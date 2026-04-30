/**
 * @fileoverview Detects Motion Event Listeners for WCAG 2.5.4
 */

/**
 * Detects device motion event listeners via runtime checks and static script scanning.
 * @param {import('playwright').Page} page - Playwright page object
 * @returns {Promise<Object>} MotionDetectionResult object with evidence and confidence
 */
export async function detectMotionEventListeners(page) {
  let runtimeCheck = { devicemotionOnHandler: false, deviceorientationOnHandler: false, jqueryMotion: false };
  try {
    runtimeCheck = await page.evaluate(() => {
      return {
        devicemotionOnHandler: typeof window.ondevicemotion === 'function',
        deviceorientationOnHandler: typeof window.ondeviceorientation === 'function',
        jqueryMotion: typeof window.$ !== 'undefined' && (window.$._data?.(window, 'events')?.devicemotion?.length > 0)
      };
    });
  } catch (err) {
    console.warn('[wcag-2.5.4] runtime check failed:', err.message);
  }

  let scriptData = { inlineMatches: [], external: [], externalUrlMatches: [] };
  try {
    scriptData = await page.evaluate(() => {
      const patterns = ['devicemotion', 'deviceorientation', 'accelerationIncludingGravity', 'rotationRate', 'beta, gamma, alpha', 'shake', 'tilt', 'gyroscope', 'accelerometer', 'motionEvent', 'orientationchange'];
      const urlPatterns = ['shake', 'tilt', 'motion', 'gyro', 'accelero', 'orientation', 'sensor'];
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
    console.warn('[wcag-2.5.4] script data collection failed:', err.message);
  }

  const externalScriptMatches = [];
  for (const ext of scriptData.external) {
     try {
        const content = await page.evaluate(async (src) => {
           try {
             const res = await fetch(src);
             if (res.ok) return await res.text();
           } catch (e) { return null; }
           return null;
        }, ext.src);

        if (content) {
           const patterns = ['devicemotion', 'deviceorientation', 'accelerationIncludingGravity', 'rotationRate', 'shake', 'tilt', 'gyroscope', 'accelerometer', 'motionEvent', 'orientationchange'];
           patterns.forEach(p => {
             if (new RegExp(p, 'i').test(content)) {
                externalScriptMatches.push({ pattern: p, scriptSrc: ext.src });
             }
           });
        }
     } catch (e) {}
  }

  const hasOnDeviceMotionHandler = runtimeCheck.devicemotionOnHandler || !!runtimeCheck.jqueryMotion;
  const hasOnDeviceOrientationHandler = runtimeCheck.deviceorientationOnHandler;

  let confidence = 'low';
  if (hasOnDeviceMotionHandler || hasOnDeviceOrientationHandler) {
     confidence = 'high';
  } else if (scriptData.inlineMatches.length > 0 || externalScriptMatches.length > 0) {
     confidence = 'medium';
  } else if (scriptData.externalUrlMatches.length === 0) {
     confidence = 'none';
  }

  const rawEvidence = [];
  if (hasOnDeviceMotionHandler) rawEvidence.push('Runtime devicemotion handler detected');
  if (hasOnDeviceOrientationHandler) rawEvidence.push('Runtime deviceorientation handler detected');
  scriptData.inlineMatches.forEach(m => rawEvidence.push(`Inline script match for '${m.pattern}': ...${m.snippet}...`));
  externalScriptMatches.forEach(m => rawEvidence.push(`External script (${m.scriptSrc}) match for '${m.pattern}'`));
  scriptData.externalUrlMatches.forEach(m => rawEvidence.push(`Script URL (${m.scriptSrc}) contains keyword '${m.keyword}'`));

  return {
    hasOnDeviceMotionHandler,
    hasOnDeviceOrientationHandler,
    inlineScriptMatches: scriptData.inlineMatches,
    externalScriptMatches,
    externalScriptUrlMatches: scriptData.externalUrlMatches,
    confidence,
    rawEvidence
  };
}