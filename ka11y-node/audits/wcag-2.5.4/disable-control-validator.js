/**
 * @fileoverview Validates the presence of a "disable motion" control
 */

/**
 * Checks if a motion disable control is present in the DOM
 * @param {import('playwright').Page} page - Playwright page object
 * @returns {Promise<{ hasDisableControl: boolean, confidence: "high" | "medium" | "low" | "none", evidence: string[] }>}
 */
export async function validateDisableControl(page) {
  try {
    const result = await page.evaluate(() => {
      const evidence = [];
      let highestConfidence = 'none';

      const checkPatterns = (text, patterns) => patterns.some(p => text.toLowerCase().includes(p.toLowerCase()));
      const highConfidencePatterns = ['disable motion', 'turn off motion', 'motion off', 'stop shaking', 'disable shake', 'モーション無効', '動き無効', 'シェイク無効'];
      const settingsPatterns = ['settings', 'preferences', '設定'];
      const motionPatterns = ['motion', 'shake', 'tilt', 'gyro', 'モーション', 'シェイク', '傾き'];
      const accessibilityPatterns = ['accessibility', 'アクセシビリティ'];

      // High Confidence Checks
      const buttonsAndInputs = Array.from(document.querySelectorAll('button, input[type="checkbox"], select'));
      for (const el of buttonsAndInputs) {
        const text = (el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '');
        if (checkPatterns(text, highConfidencePatterns)) {
          highestConfidence = 'high';
          evidence.push(`Found specific disable control: <${el.tagName.toLowerCase()}> with text "${text.trim()}"`);
        }
      }

      const links = Array.from(document.querySelectorAll('a[href]'));
      for (const a of links) {
        const text = (a.textContent || '') + ' ' + (a.getAttribute('href') || '');
        if (checkPatterns(text, settingsPatterns)) {
          if (highestConfidence === 'none' || highestConfidence === 'low') {
            highestConfidence = 'high'; // Settings link is considered high confidence by spec
            evidence.push(`Found settings link: ${a.href}`);
          }
        }
      }

      const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
      for (const cb of checkboxes) {
        const id = cb.getAttribute('id');
        const label = id ? document.querySelector(`label[for="${id}"]`) : cb.closest('label');
        if (label && checkPatterns(label.textContent || '', motionPatterns)) {
          highestConfidence = 'high';
          evidence.push(`Found checkbox associated with motion: label "${label.textContent.trim()}"`);
        }
      }

      // Medium Confidence Checks
      const switches = Array.from(document.querySelectorAll('[role="switch"]'));
      if (switches.length > 0) {
        const pageText = document.body.textContent || '';
        if (checkPatterns(pageText, motionPatterns)) {
          if (highestConfidence === 'none' || highestConfidence === 'low') highestConfidence = 'medium';
          evidence.push('Found ARIA switch on a page mentioning motion');
        }
      }

      const allElements = Array.from(document.querySelectorAll('*'));
      for (const el of allElements) {
        const ariaLabel = el.getAttribute('aria-label') || '';
        if (checkPatterns(ariaLabel, accessibilityPatterns)) {
          if (highestConfidence === 'none' || highestConfidence === 'low') highestConfidence = 'medium';
          evidence.push('Found accessibility section/control via aria-label');
        }
      }

      const details = Array.from(document.querySelectorAll('details, [role="dialog"]'));
      for (const detail of details) {
        const text = (detail.textContent || '');
        if (checkPatterns(text, settingsPatterns) && detail.querySelector('input[type="checkbox"]')) {
          if (highestConfidence === 'none' || highestConfidence === 'low') highestConfidence = 'medium';
          evidence.push('Found settings modal/details containing a checkbox');
        }
      }

      // Low Confidence Check
      const settingsIcons = Array.from(document.querySelectorAll('img, svg, i, span'));
      for (const icon of settingsIcons) {
         const classOrId = (icon.className + ' ' + icon.id).toLowerCase();
         if (checkPatterns(classOrId, settingsPatterns) || checkPatterns(icon.getAttribute('aria-label') || '', settingsPatterns)) {
            if (highestConfidence === 'none') highestConfidence = 'low';
            evidence.push('Found icon potentially linking to settings');
         }
      }

      return {
        hasDisableControl: highestConfidence === 'high' || highestConfidence === 'medium',
        confidence: highestConfidence,
        evidence
      };
    });
    return result;
  } catch (err) {
    console.warn('[wcag-2.5.4] disable control validation failed:', err.message);
    return { hasDisableControl: false, confidence: 'low', evidence: [] };
  }
}