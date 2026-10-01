// Chat welcome messages configuration based on persona and language

export const welcomeMessages = {
  EN: {
    Friendly: `Hello! 👋 I'm your assistant 😊
I'm here to help you with product documentation, specifications, and anything else you need.
How can I help you today? 🌟`,

    Professional: `Hello. 👋 I'm your assistant.
I can assist you with product documentation, specifications, and any queries you may have.
How may I support you today?`,

    Casual: `😎 Hey! 👋 I'm your assistant 😄
Need help with docs, specs, or anything else?
Just tell me. I got you! 🚀`,

    Technical: `Greetings. 👋 I'm your assistant.
I can help with product documentation, technical specifications, workflows, and system-level queries. How would you like to proceed? ⚙️📘`,
  },

  JA: {
    Friendly: `こんにちは！👋 私はあなたのアシスタントです😊
製品ドキュメントや仕様書、その他必要なことなら何でもお手伝いします。
今日はどのようなご用件でしょうか？🌟`,

    Professional: `こんにちは。👋 私はあなたのアシスタントです。
製品ドキュメントや仕様書、ご質問など、あらゆるお問い合わせに対応いたします。
本日はどのようなご用件でしょうか？`,

    Casual: `😎 おーい！👋 あなたのアシスタントです😄
ドキュメントや仕様書、その他何でもお手伝いしましょうか？
お任せください！すぐに対応しますよ！🚀`,

    Technical: `ご挨拶申し上げます。👋 私はあなたのアシスタントです。
製品ドキュメント、技術仕様書、ワークフロー、システムレベルの問い合わせなど、お手伝いできます。どのようにお進めしましょうか？ ⚙️📘`,
  },
};

/**
 * Get welcome message based on persona and language
 * @param {string} persona - The persona type (Friendly, Professional, Casual, Technical)
 * @param {string} language - The language code (EN, JA)
 * @returns {string} The welcome message
 */
export const getWelcomeMessage = (persona = "Friendly", language = "EN") => {
  // Fallback to Friendly if persona not found
  const personaKey = persona || "Friendly";
  const languageKey = language || "EN";

  // Get message, with fallbacks
  return (
    welcomeMessages[languageKey]?.[personaKey] || welcomeMessages.EN.Friendly
  );
};
