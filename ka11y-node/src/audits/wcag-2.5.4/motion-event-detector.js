/**
 * @fileoverview Detects Motion Event Listeners for WCAG 2.5.4
 */

const { extractMotionRegistry } = require('./motion-listener-detector.js');

/**
 * Detects device motion event listeners via runtime checks and static script scanning.
 * @param {import('playwright').Page} page - Playwright page object
 * @returns {Promise<Object>} MotionDetectionResult object with evidence and confidence
 */
async function detectMotionEventListeners(page) {
  const frames = page.frames();
  const results = await Promise.all(frames.map(async (frame) => {
    let runtimeCheck = { devicemotionOnHandler: false, deviceorientationOnHandler: false, jqueryMotion: false };
    try {
      runtimeCheck = await frame.evaluate(() => {
        return {
          devicemotionOnHandler: typeof window.ondevicemotion === 'function',
          deviceorientationOnHandler: typeof window.ondeviceorientation === 'function',
          jqueryMotion: typeof window.$ !== 'undefined' && (window.$._data?.(window, 'events')?.devicemotion?.length > 0)
        };
      });
    } catch (err) {
      // Frame might be detached or cross-origin
    }

    let scriptData = { inlineMatches: [], external: [], externalUrlMatches: [] };
    try {
      scriptData = await frame.evaluate(() => {
        const patterns = ['devicemotion', 'deviceorientation', 'accelerationIncludingGravity', 'rotationRate', 'beta, gamma, alpha', 'shake', 'tilt', 'gyroscope', 'accelerometer', 'motionEvent'];
        const urlPatterns = ['shake', 'tilt', 'gyro', 'accelero', 'sensor'];
        const scripts = Array.from(document.scripts);
        const inline = [];
        const external = [];

        scripts.forEach((s, idx) => {
          if (s.src) {
            external.push({ src: s.src, index: idx });
          } else {
            inline.push({ text: s.textContent || '', index: idx });
          }
        });

        const inlineMatches = [];
        inline.forEach(s => {
          patterns.forEach(p => {
            const regex = new RegExp(p.replace(/,\\s*/g, '\\s*,?\\s*'), 'i');
            const match = s.text.match(regex);
            if (match) {
               const start = Math.max(0, match.index - 50);
               const end = Math.min(s.text.length, match.index + 50);
               inlineMatches.push({ pattern: p, scriptIndex: s.index, snippet: s.text.substring(start, end).trim() });
            }
          });
        });

        const externalUrlMatches = [];
        external.forEach(s => {
          urlPatterns.forEach(p => {
            if (s.src.toLowerCase().includes(p.toLowerCase())) {
              externalUrlMatches.push({ keyword: p, scriptSrc: s.src });
            }
          });
        });

        return { inlineMatches, external, externalUrlMatches };
      });
    } catch (err) {
      // Frame might be detached or cross-origin
    }

    const externalScriptMatches = [];
    for (const ext of scriptData.external) {
       try {
          const content = await frame.evaluate(async (src) => {
             try {
               const res = await fetch(src);
               if (res.ok) return await res.text();
             } catch (e) { return null; }
             return null;
          }, ext.src);

          if (content) {
             const patterns = ['devicemotion', 'deviceorientation', 'accelerationIncludingGravity', 'rotationRate', 'shake', 'tilt', 'gyroscope', 'accelerometer', 'motionEvent'];
             patterns.forEach(p => {
               if (new RegExp(p, 'i').test(content)) {
                  externalScriptMatches.push({ pattern: p, scriptSrc: ext.src });
               }
             });
          }
       } catch (e) {}
    }

    return {
      runtimeCheck,
      scriptData,
      externalScriptMatches,
      frameUrl: frame.url()
    };
  }));

  // Read entries captured by the addEventListener monkey-patch (if it was injected).
  const addEventListenerMatches = await extractMotionRegistry(page);

  const combinedRawEvidence = [];
  let hasOnDeviceMotionHandler = false;
  let hasOnDeviceOrientationHandler = false;
  let hasAddEventListenerMotionHandler = false;
  let hasInlineMatches = false;
  let hasExternalMatches = false;
  let hasUrlMatches = false;

  const allInlineMatches = [];
  const allExternalScriptMatches = [];
  const allExternalUrlMatches = [];

  for (const entry of addEventListenerMatches) {
    if (entry.type === 'devicemotion') {
      hasOnDeviceMotionHandler = true;
      hasAddEventListenerMotionHandler = true;
      combinedRawEvidence.push(`addEventListener('devicemotion', …) registered on ${entry.target}`);
    } else if (entry.type === 'deviceorientation' || entry.type === 'deviceorientationabsolute') {
      hasOnDeviceOrientationHandler = true;
      hasAddEventListenerMotionHandler = true;
      combinedRawEvidence.push(`addEventListener('${entry.type}', …) registered on ${entry.target}`);
    } else if (entry.type === 'requestPermission') {
      // iOS 13+ explicit opt-in is a strong signal even before any listener runs.
      hasAddEventListenerMotionHandler = true;
      combinedRawEvidence.push('DeviceMotionEvent.requestPermission() invoked (iOS 13+ opt-in)');
    }
  }

  for (const res of results) {
    if (res.runtimeCheck.devicemotionOnHandler || res.runtimeCheck.jqueryMotion) {
      hasOnDeviceMotionHandler = true;
      combinedRawEvidence.push(`Runtime devicemotion handler detected in frame: ${res.frameUrl}`);
    }
    if (res.runtimeCheck.deviceorientationOnHandler) {
      hasOnDeviceOrientationHandler = true;
      combinedRawEvidence.push(`Runtime deviceorientation handler detected in frame: ${res.frameUrl}`);
    }
    res.scriptData.inlineMatches.forEach(m => {
      hasInlineMatches = true;
      allInlineMatches.push(m);
      combinedRawEvidence.push(`Inline script match for '${m.pattern}' in frame ${res.frameUrl}: ...${m.snippet}...`);
    });
    res.externalScriptMatches.forEach(m => {
      hasExternalMatches = true;
      allExternalScriptMatches.push(m);
      combinedRawEvidence.push(`External script (${m.scriptSrc}) match for '${m.pattern}' in frame ${res.frameUrl}`);
    });
    res.scriptData.externalUrlMatches.forEach(m => {
      hasUrlMatches = true;
      allExternalUrlMatches.push(m);
      combinedRawEvidence.push(`Script URL (${m.scriptSrc}) contains keyword '${m.keyword}' in frame ${res.frameUrl}`);
    });
  }

  let confidence = 'low';
  if (hasOnDeviceMotionHandler || hasOnDeviceOrientationHandler) {
     confidence = 'high';
  } else if (hasInlineMatches || hasExternalMatches) {
     confidence = 'medium';
  } else if (!hasUrlMatches) {
     confidence = 'none';
  }

  return {
    hasOnDeviceMotionHandler,
    hasOnDeviceOrientationHandler,
    hasAddEventListenerMotionHandler,
    addEventListenerMatches,
    inlineScriptMatches: allInlineMatches,
    externalScriptMatches: allExternalScriptMatches,
    externalScriptUrlMatches: allExternalUrlMatches,
    confidence,
    rawEvidence: combinedRawEvidence
  };
}

module.exports = { detectMotionEventListeners };
