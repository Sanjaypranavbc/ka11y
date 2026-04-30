/**
 * @fileoverview Detects JS libraries known to handle device motion (e.g. shake.js)
 */

/**
 * Fingerprints libraries that interact with motion/orientation sensors.
 * @param {import('playwright').Page} page - Playwright page object
 * @returns {Promise<Map<string, { confidence: string, evidence: string }>>}
 */
async function detectMotionLibraries(page) {
  let detected = new Map();
  try {
    const libs = await page.evaluate(() => {
      const found = [];
      if (typeof window.Shake !== 'undefined') found.push({ name: 'shake.js', confidence: 'high', evidence: 'window.Shake object present' });
      if (typeof window.Gyroscape !== 'undefined') found.push({ name: 'gyroscape', confidence: 'high', evidence: 'window.Gyroscape object present' });
      if (typeof window.Hammer !== 'undefined' && window.Hammer.DIRECTION_ALL) found.push({ name: 'hammer.js (motion mode)', confidence: 'medium', evidence: 'Hammer.js with DIRECTION_ALL configuration' });
      if (typeof window.DeviceMotionEvent !== 'undefined' && document.querySelector('[data-shake]')) found.push({ name: 'custom shake handler', confidence: 'medium', evidence: '[data-shake] attribute with DeviceMotionEvent present' });
      // iOS 13+ requires explicit permission for DeviceMotion. If this API is used, they almost certainly use motion.
      if (typeof window.DeviceMotionEvent !== 'undefined' && typeof window.DeviceMotionEvent.requestPermission === 'function') found.push({ name: 'iOS motion permission API', confidence: 'high', evidence: 'DeviceMotionEvent.requestPermission API called/present' });

      const scripts = Array.from(document.scripts).map(s => s.src.toLowerCase());
      for (const src of scripts) {
        if (src.includes('shake.min.js') || src.includes('shake.js')) found.push({ name: 'shake.js (CDN)', confidence: 'high', evidence: `Script URL: ${src}` });
        if (src.includes('gyroscape')) found.push({ name: 'gyroscape (CDN)', confidence: 'high', evidence: `Script URL: ${src}` });
        if (src.includes('motion-sensor')) found.push({ name: 'motion-sensor lib', confidence: 'medium', evidence: `Script URL: ${src}` });
      }
      return found;
    });

    for (const item of libs) {
      detected.set(item.name, { confidence: item.confidence, evidence: item.evidence });
    }
  } catch (err) {
    console.warn('[wcag-2.5.4] library detection failed:', err.message);
  }
  return detected;
}