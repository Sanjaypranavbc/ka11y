'use strict';

const {
  buildKeywordPattern,
  getKeywordList,
  getSharedRuleContext,
  renderLocalizedText,
} = require('./sharedAssets');

const SC = '3.3.3';
const RULE_ID = 'custom-error-suggestion';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/error-suggestion';

function _t(context, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, context, en);
}

async function run(page, context = {}) {
  const sharedContext = getSharedRuleContext(context);
  const suggestionPattern = buildKeywordPattern(
    getKeywordList('error_suggestion', 'suggestion_keywords', sharedContext)
  ) || 'please\\s+enter|must\\s+be|should\\s+be|valid\\s+email|try\\s+again|example:';
  const tersePattern = buildKeywordPattern(
    getKeywordList('error_suggestion', 'terse_keywords', sharedContext)
  ) || 'invalid|error|required|failed|wrong|incorrect|bad\\s+input|not\\s+valid';

  const data = await page.evaluate(() => {
    const formCount = document.querySelectorAll('form').length;

    // Bug fix: be more precise — require non-empty text content and some minimum length
    // to avoid false positives from decorative elements with "error" classes
    const errorSelectors = [
      '[role="alert"]',
      '[aria-live="assertive"]',
      // FP fix: use general sibling combinator scoped to known error/alert classes
      // instead of immediate next sibling (+) which may match unrelated elements.
      '[aria-invalid="true"] ~ *[class*="error"]',
      '[aria-invalid="true"] ~ *[role="alert"]',
      '[aria-invalid="true"] ~ *[aria-live]',
      '[aria-errormessage]',
    ];

    // Class/ID based selectors: scoped to form descendants to avoid false positives
    // from documentation pages and decorative elements that happen to have "error" in their class.
    const classSelectors = [
      'form .error-message', 'form .field-error', 'form .form-error', 'form .validation-error',
      'form .help-block.error', 'form [class*="error-msg"]', 'form [class*="error-text"]',
    ];

    const allSelectors = [...errorSelectors, ...classSelectors];
    const errorEls = Array.from(document.querySelectorAll(allSelectors.join(',')));

    // Also check aria-errormessage referenced elements
    for (const el of document.querySelectorAll('[aria-errormessage]')) {
      const targetId = el.getAttribute('aria-errormessage');
      if (targetId) {
        const target = document.getElementById(targetId);
        if (target && !errorEls.includes(target)) errorEls.push(target);
      }
    }

    // B21: also resolve aria-describedby on invalid inputs. Error messages are commonly
    // injected via aria-describedby pointing to an element elsewhere in the DOM (not a
    // sibling or child). Without this, the error text exists in the page but is never
    // collected, causing hasSuggestion to be computed on an incomplete set → false fail.
    for (const el of document.querySelectorAll('[aria-invalid="true"][aria-describedby]')) {
      const ids = (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
      for (const id of ids) {
        const target = document.getElementById(id);
        if (target && !errorEls.includes(target)) errorEls.push(target);
      }
    }

    // Deduplicate
    const seen = new Set();
    const allErrors = [];

    // Before main collection loop: aria-invalid elements with title attribute
    for (const el of document.querySelectorAll('[aria-invalid="true"][title]')) {
      const text = (el.getAttribute('title') || '').trim();
      if (text.length > 3 && !seen.has(el)) {
        allErrors.push(text.slice(0, 120));
        seen.add(el);
      }
    }

    for (const el of errorEls) {
      if (seen.has(el)) continue;
      seen.add(el);
      const text = (el.textContent || '').trim().replace(/\s+/g, ' ');
      // Bug fix: filter out elements with no/trivial text (icons, decorative elements)
      if (text.length > 3) {
        allErrors.push(text.slice(0, 120));
      }
    }

    return { formCount, allErrors };
  });

  const { formCount, allErrors } = data;

  if (formCount === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Error messages must suggest how to correct mistakes',
        impact: null,
        status: 'pass',
        reason: _t(sharedContext, 'No forms detected on this page.', 'このページにフォームはありません。'),
        helpUrl: HELP_URL,
      }],
    };
  }

  if (allErrors.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Error messages must suggest how to correct mistakes',
        impact: 'moderate',
        status: 'incomplete',
        reason: _t(
          sharedContext,
          '{form_count} form(s) found but no visible error messages detected. Submit with invalid data and verify error messages explain how to correct the input (e.g. "Please enter a valid email" not just "Invalid").',
          'フォームが {form_count} 件見つかりましたが、目視できるエラーメッセージは検出されませんでした。無効な値で送信し、エラーメッセージが修正方法を説明していることを確認してください（"Invalid" だけではなく、"有効なメールアドレスを入力してください" のような文言）。',
          { form_count: formCount },
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  // A message is considered terse/uninformative only when:
  //   - it matches the known terse pattern (just "Invalid", "Error", etc.), OR
  //   - it is short (< 25 chars) AND provides no recognisable correction signal.
  // Exception: short messages that contain a digit (e.g. "Enter 8+ characters"),
  // a format indicator (@, A–Z, 0–9), or specific correction words (only, format,
  // characters) are still useful guidance and must not be flagged.
  const SHORT_BUT_INFORMATIVE_RE = /\d|[@A-Za-z][-–—][A-Za-z0-9]|\b(only|format|characters?|digits?|letters?|symbols?|uppercase|lowercase|special)\b/i;
  const suggestionRe = new RegExp(suggestionPattern, 'i');
  const terseRe = new RegExp(`^(?:${tersePattern})\\.?$`, 'i');
  const errorsWithoutSuggestion = allErrors.filter(text =>
    terseRe.test(text) ||
    (!suggestionRe.test(text) && text.length < 25 && !SHORT_BUT_INFORMATIVE_RE.test(text))
  );

  if (errorsWithoutSuggestion.length > 0) {
    return {
      successCriteriaId: SC,
      rules: [{
        ruleId: RULE_ID,
        description: 'Error messages must suggest how to correct mistakes',
        impact: 'moderate',
        status: 'fail',
        reason: _t(
          sharedContext,
          '{missing_count} of {total_count} error message(s) appear to lack correction guidance: "{sample}". Provide specific instructions, not just "Invalid" or "Error".',
          'エラーメッセージ {total_count} 件のうち {missing_count} 件は修正方法の案内が不足しているように見えます: "{sample}"。"Invalid" や "Error" だけではなく、具体的な修正手順を提示してください。',
          {
            missing_count: errorsWithoutSuggestion.length,
            total_count: allErrors.length,
            sample: errorsWithoutSuggestion.slice(0, 3).join('", "'),
          },
        ),
        helpUrl: HELP_URL,
      }],
    };
  }

  return {
    successCriteriaId: SC,
    rules: [{
      ruleId: RULE_ID,
      description: 'Error messages must suggest how to correct mistakes',
      impact: null,
      status: 'pass',
      reason: _t(
        sharedContext,
        '{total_count} error message(s) checked — all appear to provide correction guidance.',
        'エラーメッセージ {total_count} 件を確認し、いずれも修正方法の案内が含まれているように見えます。',
        { total_count: allErrors.length },
      ),
      helpUrl: HELP_URL,
    }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL };
