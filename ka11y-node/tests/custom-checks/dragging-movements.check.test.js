'use strict';

const { run } = require('../../src/custom-checks/dragging-movements.check');

function makePage(data) {
  return { evaluate: jest.fn().mockResolvedValue(data) };
}

describe('dragging-movements.check (WCAG 2.5.7)', () => {
  test('passes when no drag-and-drop is detected', async () => {
    const page = makePage({ draggables: [], hasLibraryDnd: false, libraryCount: 0 });
    const result = await run(page);
    expect(result.successCriteriaId).toBe('2.5.7');
    expect(result.rules[0].status).toBe('pass');
    expect(result.rules[0].ruleId).toBe('custom-dragging-movements');
    expect(result.rules[0].reason).toContain('No drag');
  });

  test('returns incomplete when draggable without alternative is found', async () => {
    const page = makePage({
      draggables: [{ html: '<div draggable="true">Item</div>', hasAlternative: false, source: 'native' }],
      hasLibraryDnd: false,
      libraryCount: 0,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].impact).toBe('serious');
  });

  test('passes when draggable has pointer alternative', async () => {
    const page = makePage({
      draggables: [{ html: '<div draggable="true"><button>Move up</button></div>', hasAlternative: true, source: 'native' }],
      hasLibraryDnd: false,
      libraryCount: 0,
    });
    const result = await run(page);
    expect(result.rules[0].status).toBe('pass');
  });

  test('returns incomplete when D&D library is detected', async () => {
    const page = makePage({ draggables: [], hasLibraryDnd: true, libraryCount: 2 });
    const result = await run(page);
    expect(result.rules[0].status).toBe('incomplete');
    expect(result.rules[0].reason).toContain('D&D library');
  });

  // FP fix: empty data-rbd-draggable-id tests
  describe('FP fix: empty data-rbd-draggable-id must not be flagged', () => {
    test('empty data-rbd-draggable-id="" should NOT be counted as a draggable item', async () => {
      // Simulate: the browser-side filter runs and removes empty-id elements,
      // resulting in libraryCount: 0 (no actual draggable items found)
      const page = makePage({ draggables: [], hasLibraryDnd: false, libraryCount: 0 });
      const result = await run(page);
      expect(result.rules[0].status).toBe('pass');
      expect(result.rules[0].reason).toContain('No drag');
    });

    test('non-empty data-rbd-draggable-id="item-1" WITH no alternative SHOULD be flagged', async () => {
      // Simulate: browser-side code finds 1 library draggable with non-empty id
      const page = makePage({ draggables: [], hasLibraryDnd: true, libraryCount: 1 });
      const result = await run(page);
      expect(result.rules[0].status).toBe('incomplete');
      expect(result.rules[0].impact).toBe('serious');
    });

    test('FP fix: source filters out empty data-rbd-draggable-id', () => {
      const src = require('fs').readFileSync(
        require('path').resolve(__dirname, '../../src/custom-checks/dragging-movements.check.js'),
        'utf8'
      );
      // Verify the source checks for empty attribute value
      expect(src).toMatch(/rbdId.*trim.*===\s*''|trim.*===\s*''.*rbdId/);
    });
  });
});