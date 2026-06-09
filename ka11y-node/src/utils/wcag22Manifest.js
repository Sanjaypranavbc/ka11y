'use strict';

/**
 * WCAG 2.1 (78 criteria) and WCAG 2.2 (86 criteria) manifest.
 *
 * Differences:
 *   - WCAG 2.2 removed 4.1.1 Parsing (marked wcag22: false)
 *   - WCAG 2.2 added 9 new criteria (marked wcag21: false)
 *
 * canAutomate: false = requires human sensory evaluation, live session
 *              context, or content-intent judgment — no Node.js check possible.
 */

const _ALL = [
  // ── Principle 1: Perceivable ──────────────────────────────────────────────
  { sc: '1.1.1',  name: 'Non-text Content',                             level: 'A',   principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.2.1',  name: 'Audio-only and Video-only (Prerecorded)',      level: 'A',   principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.2.2',  name: 'Captions (Prerecorded)',                       level: 'A',   principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.2.3',  name: 'Audio Description or Media Alternative',       level: 'A',   principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.2.4',  name: 'Captions (Live)',                              level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.2.5',  name: 'Audio Description (Prerecorded)',              level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.2.6',  name: 'Sign Language (Prerecorded)',                  level: 'AAA', principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: false },
  { sc: '1.2.7',  name: 'Extended Audio Description (Prerecorded)',     level: 'AAA', principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.2.8',  name: 'Media Alternative (Prerecorded)',              level: 'AAA', principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.2.9',  name: 'Audio-only (Live)',                            level: 'AAA', principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.3.1',  name: 'Info and Relationships',                       level: 'A',   principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.3.2',  name: 'Meaningful Sequence',                          level: 'A',   principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.3.3',  name: 'Sensory Characteristics',                      level: 'A',   principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.3.4',  name: 'Orientation',                                  level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.3.5',  name: 'Identify Input Purpose',                       level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.3.6',  name: 'Identify Purpose',                             level: 'AAA', principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.1',  name: 'Use of Color',                                 level: 'A',   principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.2',  name: 'Audio Control',                                level: 'A',   principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.3',  name: 'Contrast (Minimum)',                           level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.4',  name: 'Resize Text',                                  level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.5',  name: 'Images of Text',                               level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.6',  name: 'Contrast (Enhanced)',                          level: 'AAA', principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.7',  name: 'Low or No Background Audio',                   level: 'AAA', principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: false },
  { sc: '1.4.8',  name: 'Visual Presentation',                          level: 'AAA', principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.9',  name: 'Images of Text (No Exception)',                level: 'AAA', principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.10', name: 'Reflow',                                       level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.11', name: 'Non-text Contrast',                            level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.12', name: 'Text Spacing',                                 level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '1.4.13', name: 'Content on Hover or Focus',                    level: 'AA',  principle: 'Perceivable',    wcag21: true,  wcag22: true,  canAutomate: true  },
  // ── Principle 2: Operable ─────────────────────────────────────────────────
  { sc: '2.1.1',  name: 'Keyboard',                                     level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.1.2',  name: 'No Keyboard Trap',                             level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.1.3',  name: 'Keyboard (No Exception)',                      level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.1.4',  name: 'Character Key Shortcuts',                      level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.2.1',  name: 'Timing Adjustable',                            level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.2.2',  name: 'Pause, Stop, Hide',                            level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.2.3',  name: 'No Timing',                                    level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: false },
  { sc: '2.2.4',  name: 'Interruptions',                                level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: false },
  { sc: '2.2.5',  name: 'Re-authenticating',                            level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: false },
  { sc: '2.2.6',  name: 'Timeouts',                                     level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: false },
  { sc: '2.3.1',  name: 'Three Flashes or Below Threshold',             level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.3.2',  name: 'Three Flashes',                                level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.3.3',  name: 'Animation from Interactions',                  level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.1',  name: 'Bypass Blocks',                                level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.2',  name: 'Page Titled',                                  level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.3',  name: 'Focus Order',                                  level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.4',  name: 'Link Purpose (In Context)',                    level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.5',  name: 'Multiple Ways',                                level: 'AA',  principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.6',  name: 'Headings and Labels',                          level: 'AA',  principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.7',  name: 'Focus Visible',                                level: 'AA',  principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.8',  name: 'Location',                                     level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.9',  name: 'Link Purpose (Link Only)',                     level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.10', name: 'Section Headings',                             level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.4.11', name: 'Focus Not Obscured (Minimum)',                 level: 'AA',  principle: 'Operable',       wcag21: false, wcag22: true,  canAutomate: true  },
  { sc: '2.4.12', name: 'Focus Not Obscured (Enhanced)',                level: 'AAA', principle: 'Operable',       wcag21: false, wcag22: true,  canAutomate: true  },
  { sc: '2.4.13', name: 'Focus Appearance',                             level: 'AAA', principle: 'Operable',       wcag21: false, wcag22: true,  canAutomate: true  },
  { sc: '2.5.1',  name: 'Pointer Gestures',                             level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.5.2',  name: 'Pointer Cancellation',                         level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.5.3',  name: 'Label in Name',                                level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.5.4',  name: 'Motion Actuation',                             level: 'A',   principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.5.5',  name: 'Target Size (Enhanced)',                       level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.5.6',  name: 'Concurrent Input Mechanisms',                  level: 'AAA', principle: 'Operable',       wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '2.5.7',  name: 'Dragging Movements',                           level: 'AA',  principle: 'Operable',       wcag21: false, wcag22: true,  canAutomate: true  },
  { sc: '2.5.8',  name: 'Target Size (Minimum)',                        level: 'AA',  principle: 'Operable',       wcag21: false, wcag22: true,  canAutomate: true  },
  // ── Principle 3: Understandable ───────────────────────────────────────────
  { sc: '3.1.1',  name: 'Language of Page',                             level: 'A',   principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.1.2',  name: 'Language of Parts',                            level: 'AA',  principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.1.3',  name: 'Unusual Words',                                level: 'AAA', principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.1.4',  name: 'Abbreviations',                                level: 'AAA', principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.1.5',  name: 'Reading Level',                                level: 'AAA', principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.1.6',  name: 'Pronunciation',                                level: 'AAA', principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.2.1',  name: 'On Focus',                                     level: 'A',   principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.2.2',  name: 'On Input',                                     level: 'A',   principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.2.3',  name: 'Consistent Navigation',                        level: 'AA',  principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.2.4',  name: 'Consistent Identification',                    level: 'AA',  principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.2.5',  name: 'Change on Request',                            level: 'AAA', principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.2.6',  name: 'Consistent Help',                              level: 'A',   principle: 'Understandable', wcag21: false, wcag22: true,  canAutomate: true  },
  { sc: '3.3.1',  name: 'Error Identification',                         level: 'A',   principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.3.2',  name: 'Labels or Instructions',                       level: 'A',   principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.3.3',  name: 'Error Suggestion',                             level: 'AA',  principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.3.4',  name: 'Error Prevention (Legal, Financial, Data)',    level: 'AA',  principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.3.5',  name: 'Help',                                         level: 'AAA', principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.3.6',  name: 'Error Prevention (All)',                       level: 'AAA', principle: 'Understandable', wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '3.3.7',  name: 'Redundant Entry',                              level: 'A',   principle: 'Understandable', wcag21: false, wcag22: true,  canAutomate: true  },
  { sc: '3.3.8',  name: 'Accessible Authentication (Minimum)',          level: 'AA',  principle: 'Understandable', wcag21: false, wcag22: true,  canAutomate: true  },
  { sc: '3.3.9',  name: 'Accessible Authentication (Enhanced)',         level: 'AAA', principle: 'Understandable', wcag21: false, wcag22: true,  canAutomate: true  },
  // ── Principle 4: Robust ───────────────────────────────────────────────────
  // 4.1.1 Parsing: present in WCAG 2.1, removed in WCAG 2.2
  { sc: '4.1.1',  name: 'Parsing',                                      level: 'A',   principle: 'Robust',         wcag21: true,  wcag22: false, canAutomate: true  },
  { sc: '4.1.2',  name: 'Name, Role, Value',                            level: 'A',   principle: 'Robust',         wcag21: true,  wcag22: true,  canAutomate: true  },
  { sc: '4.1.3',  name: 'Status Messages',                              level: 'AA',  principle: 'Robust',         wcag21: true,  wcag22: true,  canAutomate: true  },
];

/** SC IDs that cannot be automated in Node.js — require human judgment. */
const CANNOT_AUTOMATE_SC = new Set(
  _ALL.filter(c => !c.canAutomate).map(c => c.sc)
);

const MANUAL_ONLY_REASON = {
  '1.2.6': 'Quality of sign language requires human expertise to evaluate',
  '1.4.7': 'Requires listening to and measuring audio decibel levels',
  '2.2.3': 'Requires understanding the full application UX flow and intent',
  '2.2.4': 'Requires human judgment on notification intent (emergency vs non-emergency)',
  '2.2.5': 'Requires real authenticated session simulation with timeout verification',
  '2.2.6': 'Requires live session behavior context to verify timeout warnings',
};

/**
 * Returns criteria filtered to the requested WCAG version.
 * @param {'2.1'|'2.2'} version
 * @returns {Array<object>}
 */
function getCriteria(version = '2.2') {
  if (version === '2.1') return _ALL.filter(c => c.wcag21);
  return _ALL.filter(c => c.wcag22);
}

/**
 * Returns a single criterion by SC id, regardless of version.
 * @param {string} sc  e.g. "1.1.1"
 */
function getCriterion(sc) {
  return _ALL.find(c => c.sc === sc) || null;
}

module.exports = { getCriteria, getCriterion, CANNOT_AUTOMATE_SC, MANUAL_ONLY_REASON };
