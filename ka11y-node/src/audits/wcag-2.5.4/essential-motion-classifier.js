/**
 * @fileoverview Heuristically classifies whether motion actuation is essential (and thus exempt)
 */

/**
 * Checks if the motion is likely essential (like a pedometer or VR)
 * @param {import('playwright').Page} page - Playwright page object
 * @param {Object} motionEvidence - Evidence from the detector
 * @returns {Promise<{ likelyEssential: boolean, reason: string, softSignals: string[] }>}
 */
async function classifyMotionAsEssential(page, motionEvidence) {
  try {
    const data = await page.evaluate(() => {
       const hasExplicitOptIn = !!document.querySelector('[data-wcag-motion-essential="true"]');
       const title = (document.title || '').toLowerCase();
       const h1s = Array.from(document.querySelectorAll('h1')).map(h => h.textContent.toLowerCase()).join(' ');
       const metas = Array.from(document.querySelectorAll('meta[name="description"]')).map(m => (m.content || '').toLowerCase()).join(' ');
       const text = `${title} ${h1s} ${metas}`;
       
       // Improvement: Detect 3D contexts natively
       const hasWebGL = Array.from(document.querySelectorAll('canvas')).some(c => {
         try {
           return !!(c.getContext('webgl') || c.getContext('webgl2'));
         } catch(e) { return false; }
       });
       
       // Improvement: Detect Schema.org VideoGame definitions
       const hasGameSchema = Array.from(document.querySelectorAll('script[type="application/ld+json"]')).some(s => {
         try {
           const d = JSON.parse(s.textContent);
           return d['@type'] === 'VideoGame' || d.applicationCategory === 'Game';
         } catch(e) { return false; }
       });

       const hasAriaLive = !!document.querySelector('[aria-live]');
       const hasAriaRoles = !!document.querySelector('[role="application"], [role="status"]');

       return { hasExplicitOptIn, text, hasCanvas: hasWebGL || !!document.querySelector('canvas'), hasWebGL, hasGameSchema, hasAriaLive, hasAriaRoles };
    });

    const text = data.text;
    const softSignals = [];

    if (/\b(steps|pedometer|fitness|workout|calories|歩数|フィットネス)\b/.test(text)) {
       softSignals.push('Pedometer / fitness context detected');
    }
    if (/\b(gps|compass|ar|augmented reality|コンパス)\b/.test(text)) {
       softSignals.push('Navigation / compass context detected');
    }
    if (/\b(level|measure|tilt angle|水平器)\b/.test(text)) {
       softSignals.push('Spirit level / measurement tool context detected');
    }
    if (/(vr|virtual reality|webxr)/.test(text) || (text.includes('three.js') && text.includes('camera'))) {
       softSignals.push('VR / AR experience context detected');
    }
    if (data.hasGameSchema || (data.hasCanvas && /game/.test(text))) {
       softSignals.push('Game context (Schema/Canvas) detected');
    }
    if (data.hasWebGL) {
       softSignals.push('WebGL 3D context detected (often requires device orientation)');
    }
    if (data.hasAriaLive && data.hasAriaRoles) {
       softSignals.push('Accessibility-supported AT context detected');
    }

    const isEssential = data.hasExplicitOptIn;
    const reason = isEssential 
      ? 'Explicit opt-in attribute [data-wcag-motion-essential="true"] found' 
      : 'no explicit opt-in attribute';

    return { 
      likelyEssential: isEssential, 
      reason: reason,
      softSignals: softSignals
    };
  } catch (err) {
    console.warn('[wcag-2.5.4] classification failed:', err.message);
    return { likelyEssential: false, reason: 'classification-error', softSignals: [] };
  }
}

module.exports = { classifyMotionAsEssential };
