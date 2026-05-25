/**
 * @fileoverview Validates the presence of a "disable motion" control
 */

/**
 * Checks if a motion disable control is present in the DOM
 * @param {import('playwright').Page} page - Playwright page object
 * @returns {Promise<{ hasDisableControl: boolean, confidence: "high" | "medium" | "low" | "none", evidence: string[] }>}
 */
async function validateDisableControl(page) {
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
          // Check for motion keywords in nearby text (same parent or siblings)
          const parent = a.parentElement;
          let hasMotionNearby = false;
          if (parent) {
            const nearbyText = parent.textContent || '';
            if (checkPatterns(nearbyText, motionPatterns) || checkPatterns(nearbyText, accessibilityPatterns)) {
              hasMotionNearby = true;
            }
          }

          // A settings/preferences link only counts as evidence of a
          // motion-disable control when motion (or accessibility) keywords
          // appear in the same subtree. A bare account-settings link is NOT
          // evidence — recording it produced misleading "generic settings
          // link" findings and false-confidence on unrelated pages.
          if (hasMotionNearby) {
            if (highestConfidence === 'none' || highestConfidence === 'low') {
              highestConfidence = 'medium';
              evidence.push(`Found settings link with motion-related context: ${a.href}`);
            }
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
      const switches = Array.from(document.querySelectorAll('[role="switch"], [aria-pressed="true"], [aria-pressed="false"]'));
      if (switches.length > 0) {
        const pageText = document.body.textContent || '';
        if (checkPatterns(pageText, motionPatterns)) {
          if (highestConfidence === 'none' || highestConfidence === 'low') highestConfidence = 'medium';
          evidence.push('Found ARIA switch or pressed-toggle on a page mentioning motion');
        }
        // Deep Check: Does the switch specifically reference motion?
        for (const sw of switches) {
           const label = (sw.getAttribute('aria-label') || sw.textContent || '').trim();
           if (checkPatterns(label, motionPatterns)) {
              highestConfidence = 'high';
              evidence.push(`Found ARIA switch/toggle specifically for motion: "${label}"`);
           }
        }
      }

      // Constrain "accessibility-section" detection to landmarks and interactive
      // controls — and only count it as evidence if the same subtree mentions
      // a motion keyword. The previous implementation walked
      // `document.querySelectorAll('*')` and produced a medium-confidence pass
      // on any page with an "Accessibility" landmark regardless of its content.
      const accessibilityRegions = Array.from(document.querySelectorAll(
        'nav, aside, section, dialog, button, a[href], [role="region"], [role="navigation"], [role="dialog"], [role="menu"]'
      ));
      for (const el of accessibilityRegions) {
        const ariaLabel = el.getAttribute('aria-label') || '';
        if (!checkPatterns(ariaLabel, accessibilityPatterns)) continue;

        const subtreeText = (el.textContent || '');
        if (!checkPatterns(subtreeText, motionPatterns)) continue;

        if (highestConfidence === 'none' || highestConfidence === 'low') {
          highestConfidence = 'medium';
        }
        evidence.push(`Found accessibility region "${ariaLabel.trim()}" mentioning motion keywords`);
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

module.exports = { validateDisableControl };
