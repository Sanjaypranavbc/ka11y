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
});