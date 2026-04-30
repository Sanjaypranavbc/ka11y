/**
 * @fileoverview Heuristically classifies whether motion actuation is essential (and thus exempt)
 */

/**
 * Checks if the motion is likely essential (like a pedometer or VR)
 * @param {import('playwright').Page} page - Playwright page object
 * @param {Object} motionEvidence - Evidence from the detector
 * @returns {Promise<{ likelyEssential: boolean, reason: string | null }>}
 */
export async function classifyMotionAsEssential(page, motionEvidence) {
  try {
    const data = await page.evaluate(() => {
       const title = (document.title || '').toLowerCase();
       const h1s = Array.from(document.querySelectorAll('h1')).map(h => h.textContent.toLowerCase()).join(' ');
       const metas = Array.from(document.querySelectorAll('meta[name="description"]')).map(m => (m.content || '').toLowerCase()).join(' ');
       const text = `${title} ${h1s} ${metas}`;
       const hasCanvas = !!document.querySelector('canvas');
       const hasAriaLive = !!document.querySelector('[aria-live]');
       const hasAriaRoles = !!document.querySelector('[role="application"], [role="status"]');

       return { text, hasCanvas, hasAriaLive, hasAriaRoles };
    });

    const text = data.text;

    if (/\b(steps|pedometer|fitness|workout|calories|歩数|フィットネス)\b/.test(text)) {
       return { likelyEssential: true, reason: 'Pedometer / fitness context detected' };
    }
    if (/\b(gps|compass|ar|augmented reality|コンパス)\b/.test(text)) {
       return { likelyEssential: true, reason: 'Navigation / compass context detected' };
    }
    if (/\b(level|measure|tilt angle|水平器)\b/.test(text)) {
       return { likelyEssential: true, reason: 'Spirit level / measurement tool context detected' };
    }
    if (/(vr|virtual reality|webxr)/.test(text) || (text.includes('three.js') && text.includes('camera'))) {
       return { likelyEssential: true, reason: 'VR / AR experience context detected' };
    }
    if (data.hasCanvas && /game/.test(text)) {
       return { likelyEssential: true, reason: 'Canvas game context detected' };
    }
    if (data.hasAriaLive && data.hasAriaRoles) {
       return { likelyEssential: true, reason: 'Accessibility-supported AT context detected' };
    }

    return { likelyEssential: false, reason: null };
  } catch (err) {
    console.warn('[wcag-2.5.4] classification failed:', err.message);
    return { likelyEssential: false, reason: null };
  }
}