import React, { useRef, useState, useEffect } from "react";
import { Form, InputGroup, Spinner } from "react-bootstrap";
import { FiAlertCircle } from "react-icons/fi";
import attach from "../assets/icons/attach.png";
import mic from "../assets/icons/mic.png";
import LanguageSelector, { useLanguage } from "../Components/LanguageSelector";
import send from "../assets/icons/send.png";
import send_voice from "../assets/icons/send-voice.png";
import axiosInstance from "../utils/axios";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getWelcomeMessage } from "../utils/chatWelcomeMessages";

/**
 * ChatWindow
 * - Detects base64 images in backend response
 * - Converts them to Blob URLs
 * - Renders images and revokes old Blob URLs
 * - Generates unique thread_id for each chat session
 *
 * Extensive console.log debug messages included.
 */
function ChatWindow() {
  const { language } = useLanguage();
  const textareaRef = useRef(null);
  const messagesEndRef = useRef(null);
  const [message, setMessage] = useState("");

  // Get chat title from sessionStorage for initial message
  const chatTitle = sessionStorage.getItem("chatCollectionName") || "BS9000";

  // Get persona preference and chat language from sessionStorage
  const getInitialWelcomeMessage = () => {
    const persona = sessionStorage.getItem("prefText") || "Friendly";
    const chatLang = sessionStorage.getItem("chatLang") || "en";
    // Map chatLang to language code (en -> EN, jp -> JA)
    const languageCode = chatLang.toLowerCase() === "jp" ? "JA" : "EN";
    return getWelcomeMessage(persona, languageCode);
  };

  // Generate unique thread_id for this chat session
  const generateThreadId = () => {
    const timestamp = Date.now();
    const randomStr = Math.random().toString(36).substring(2, 15);
    const threadId = `thread_${timestamp}_${randomStr}`;
    console.log("[DEBUG] Generated new thread_id:", threadId);
    return threadId;
  };

  // Initialize thread_id once when component mounts
  const [threadId] = useState(() => generateThreadId());

  const [messages, setMessages] = useState([
    {
      id: 1,
      type: "bot",
      text: getInitialWelcomeMessage(),
      time: new Date().toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      }),
      error: false,
      images: [], // no images on initial message
    },
  ]);
  const [loading, setLoading] = useState(false);

  // Keep a ref to previously-known blob URLs so we can revoke removed ones
  const previousBlobUrlsRef = useRef(new Set());

  // Log thread_id when component mounts
  useEffect(() => {
    console.log("[DEBUG] Chat session started with thread_id:", threadId);
  }, [threadId]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    console.log("[DEBUG] messages changed, scrolling to bottom.");
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Revoke Blob URLs that are no longer present in messages
  useEffect(() => {
    console.log("[DEBUG] Running Blob URL cleanup effect.");
    const currentBlobUrls = new Set();
    messages.forEach((m) => {
      if (Array.isArray(m.images)) {
        m.images.forEach((u) => currentBlobUrls.add(u));
      }
    });

    // Revoke any previously created blob URL that is no longer in current messages
    const prev = previousBlobUrlsRef.current;
    prev.forEach((url) => {
      if (!currentBlobUrls.has(url)) {
        try {
          console.log(
            `[DEBUG] Revoking blob URL (removed from messages): ${url}`
          );
          URL.revokeObjectURL(url);
        } catch (err) {
          console.warn("[DEBUG] Failed to revoke URL:", url, err);
        }
        prev.delete(url);
      }
    });

    // Add any new URLs to prev set
    currentBlobUrls.forEach((url) => {
      if (!prev.has(url)) {
        console.log(`[DEBUG] Registering new blob URL: ${url}`);
        prev.add(url);
      }
    });

    // Save back (ref already mutated)
    previousBlobUrlsRef.current = prev;

    // No cleanup function (we revoke on changes and also in unmount below)
  }, [messages]);

  // Revoke all blob URLs on unmount
  useEffect(() => {
    return () => {
      console.log(
        "[DEBUG] Component unmounting: revoking all stored blob URLs."
      );
      previousBlobUrlsRef.current.forEach((url) => {
        try {
          URL.revokeObjectURL(url);
          console.log("[DEBUG] Revoked:", url);
        } catch (err) {
          console.warn("[DEBUG] Error revoking on unmount:", url, err);
        }
      });
      previousBlobUrlsRef.current.clear();
    };
  }, []);

  // Auto-expand handler - disabled for mobile responsive
  const handleInput = (e) => {
    setMessage(e.target.value);
  };

  // ----- Helper utilities for base64 detection and blob conversion -----

  // Find explicit data:image/...;base64,... URIs
  const findDataImageUris = (text) => {
    if (!text || typeof text !== "string") return [];
    const dataUriRegex =
      /(data:image\/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+(?:={0,2}))/g;
    const matches = [];
    let m;
    while ((m = dataUriRegex.exec(text)) !== null) {
      console.log("[DEBUG] Found explicit data URI at index", m.index);
      matches.push(m[0]);
    }
    return matches;
  };

  // Try to find plain base64 blocks that look like PNG/JPEG (no data: prefix)
  // This looks for long base64 sequences and inspects signature.
  const findPlainBase64Images = (text) => {
    if (!text || typeof text !== "string") return [];
    // find candidate long base64 chunks (adjust length if necessary)
    const plainBase64Regex = /([A-Za-z0-9+/]{100,}={0,2})/g;
    const matches = [];
    let m;
    while ((m = plainBase64Regex.exec(text)) !== null) {
      const chunk = m[0];
      // Check common signatures: PNG -> "iVBOR" ; JPEG -> "/9j/"
      if (chunk.startsWith("iVBOR") || chunk.startsWith("/9j/")) {
        console.log(
          "[DEBUG] Found plain base64 candidate starting with:",
          chunk.slice(0, 10)
        );
        // prefix with appropriate data URI
        if (chunk.startsWith("iVBOR"))
          matches.push("data:image/png;base64," + chunk);
        else if (chunk.startsWith("/9j/"))
          matches.push("data:image/jpeg;base64," + chunk);
      }
    }
    return matches;
  };

  // Convert data URI (data:image/..;base64,...) -> Blob URL
  const createBlobUrlFromDataUri = (dataUri) => {
    try {
      console.log(
        "[DEBUG] Converting data URI to Blob URL (starting):",
        dataUri.slice(0, 80) + "..."
      );
      const splitIndex = dataUri.indexOf(",");
      const meta = dataUri.substring(0, splitIndex);
      const base64Data = dataUri.substring(splitIndex + 1);
      // infer mime
      let mime = "image/png";
      const mimeMatch = meta.match(/data:([^;]+);base64/);
      if (mimeMatch && mimeMatch[1]) {
        mime = mimeMatch[1];
      }
      console.log("[DEBUG] Inferred MIME:", mime);

      // Decode base64 to binary
      const byteCharacters = atob(base64Data);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: mime });
      const url = URL.createObjectURL(blob);
      console.log("[DEBUG] Created blob URL:", url);
      return url;
    } catch (err) {
      console.error("[DEBUG] Error converting data URI to blob URL:", err);
      return null;
    }
  };

  // Extract images (returns array of dataUris including implicit ones prefixed)
  const extractImageDataUrisFromText = (text) => {
    console.log("[DEBUG] Extracting image data URIs from text (start).");
    const explicit = findDataImageUris(text);
    if (explicit.length) {
      console.log(`[DEBUG] Found ${explicit.length} explicit data URI(s).`);
      return explicit;
    }
    const plain = findPlainBase64Images(text);
    if (plain.length) {
      console.log(
        `[DEBUG] Found ${plain.length} plain base64 image(s) and prefixed them.`
      );
      return plain;
    }
    console.log("[DEBUG] No image data URIs found in text.");
    return [];
  };

  // Render message content: text + images (images property is expected to contain blob URLs)
  const renderMessageContent = (msg) => {
    // msg.text may contain placeholders, the images array holds blob URLs.
    const text =
      msg &&
      (typeof msg.text === "string" ? msg.text : JSON.stringify(msg.text));
    const images = Array.isArray(msg.images) ? msg.images : [];

    console.log(
      "[DEBUG] Rendering message content for id=",
      msg.id,
      " images count=",
      images.length
    );

    const nodes = [];

    if (text) {
      // If text contains placeholders like [image:0], we split accordingly.
      // Otherwise render entire text above images.
      if (/\[image:\d+\]/.test(text) && images.length > 0) {
        // split by placeholders and interleave
        const regex = /(\[image:\d+\])/g;
        const parts = text.split(regex);
        parts.forEach((part, idx) => {
          const placeholderMatch = part.match(/^\[image:(\d+)\]$/);
          if (placeholderMatch) {
            const imageIndex = parseInt(placeholderMatch[1], 10);
            const url = images[imageIndex];
            if (url) {
              nodes.push(
                <div
                  key={`img-${msg.id}-${idx}`}
                  style={{
                    margin: "8px 0",
                    textAlign: msg.type === "bot" ? "center" : "left",
                  }}
                >
                  <img
                    src={url}
                    alt={`embedded-${imageIndex}`}
                    style={{
                      display: "inline-block",
                      maxWidth: "720px",
                      maxHeight: "480px",
                    }}
                    onLoad={() =>
                      console.log(
                        `[DEBUG] Image loaded for message ${msg.id} index ${imageIndex}`
                      )
                    }
                    onError={(e) =>
                      console.error(
                        `[DEBUG] Image failed to load for message ${msg.id} index ${imageIndex}`,
                        e
                      )
                    }
                  />
                </div>
              );
            } else {
              nodes.push(
                <span key={`txt-${msg.id}-${idx}`}>[missing image]</span>
              );
            }
          } else {
            // Render text as markdown
            nodes.push(
              <div key={`txt-${msg.id}-${idx}`} className="markdown-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {part}
                </ReactMarkdown>
              </div>
            );
          }
        });
      } else {
        // No placeholders / or no images: render text as markdown block and images after
        nodes.push(
          <div key={`txt-${msg.id}`} className="markdown-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          </div>
        );
        images.forEach((url, i) => {
          nodes.push(
            <div
              key={`img-${msg.id}-${i}`}
              style={{
                marginTop: 8,
                textAlign: msg.type === "bot" ? "center" : "left",
              }}
            >
              <img
                src={url}
                alt={`embedded-${i}`}
                style={{
                  display: "inline-block",
                  maxWidth: "720px",
                  maxHeight: "480px",
                }}
                onLoad={() =>
                  console.log(
                    `[DEBUG] Image loaded for message ${msg.id} index ${i}`
                  )
                }
                onError={(e) =>
                  console.error(
                    `[DEBUG] Image failed to load for message ${msg.id} index ${i}`,
                    e
                  )
                }
              />
            </div>
          );
        });
      }
    } else if (images.length > 0) {
      // No text (rare) but images present — render images
      images.forEach((url, i) => {
        nodes.push(
          <div
            key={`img-${msg.id}-${i}`}
            style={{
              marginTop: 8,
              textAlign: msg.type === "bot" ? "center" : "left",
            }}
          >
            <img
              src={url}
              alt={`embedded-${i}`}
              style={{
                display: "inline-block",
                maxWidth: "720px",
                maxHeight: "480px",
              }}
              onLoad={() =>
                console.log(
                  `[DEBUG] Image loaded for message ${msg.id} index ${i}`
                )
              }
              onError={(e) =>
                console.error(
                  `[DEBUG] Image failed to load for message ${msg.id} index ${i}`,
                  e
                )
              }
            />
          </div>
        );
      });
    } else {
      // fallback - render as markdown
      nodes.push(
        <div key={`txt-${msg.id}`} className="markdown-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      );
    }

    return nodes;
  };

  // ----- End helpers -----

  const handleSendMessage = async (e) => {
    e.preventDefault();

    if (!message.trim()) return;

    const userMessage = {
      id: Date.now(),
      type: "user",
      text: message,
      time: new Date().toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      }),
      error: false,
      images: [],
    };

    // Add user message to chat
    setMessages((prev) => [...prev, userMessage]);
    const currentMessage = message;
    setMessage("");

    try {
      setLoading(true);

      // Get user data from localStorage
      const userDataString = localStorage.getItem("token");
      if (!userDataString) {
        throw new Error("User not logged in. Please login again.");
      }

      const userData = JSON.parse(userDataString);
      const { user_id } = userData;

      console.log(
        "[DEBUG] Sending POST to chat API for user:",
        user_id,
        "message:",
        currentMessage,
        "thread_id:",
        threadId
      );

      const response = await axiosInstance.post(`/users/${user_id}/chat`, {
        message: currentMessage,
        user_id: user_id,
        thread_id: threadId, // Now sends the unique thread_id for this session
      });

      console.log("[DEBUG] Received response from backend:", response);

      // Determine text content from response.data safely
      let rawContent = "";
      if (!response || response.data === undefined || response.data === null) {
        rawContent = "No response from server.";
        console.warn(
          "[DEBUG] response.data is empty or undefined, using fallback text."
        );
      } else if (typeof response.data === "string") {
        rawContent = response.data;
        console.log("[DEBUG] response.data is string (used as rawContent).");
      } else if (typeof response.data === "object") {
        // Try some common fields
        if (typeof response.data.message === "string") {
          rawContent = response.data.message;
          console.log("[DEBUG] response.data.message used as rawContent.");
        } else if (typeof response.data.text === "string") {
          rawContent = response.data.text;
          console.log("[DEBUG] response.data.text used as rawContent.");
        } else {
          rawContent = JSON.stringify(response.data);
          console.log(
            "[DEBUG] response.data is object, stringified for rawContent."
          );
        }
      } else {
        rawContent = String(response.data);
        console.log("[DEBUG] response.data coerced to string for rawContent.");
      }

      console.log(
        "[DEBUG] rawContent (first 400 chars):",
        rawContent.slice(0, 400)
      );

      // Extract any image data URIs (explicit or implicit)
      const dataUris = extractImageDataUrisFromText(rawContent);

      const imagesBlobUrls = [];
      let sanitizedText = rawContent;

      if (dataUris.length) {
        console.log(
          `[DEBUG] Converting ${dataUris.length} data URI(s) to Blob URLs.`
        );
        // Convert each to blob URL and replace in text with placeholder
        dataUris.forEach((dataUri, idx) => {
          const blobUrl = createBlobUrlFromDataUri(dataUri);
          if (blobUrl) {
            imagesBlobUrls.push(blobUrl);
            // Replace only the first occurrence to preserve multiple identical images if any
            sanitizedText = sanitizedText.replace(dataUri, `[image:${idx}]`);
            console.log(
              `[DEBUG] Replaced dataUri with placeholder [image:${idx}]`
            );
          } else {
            console.warn(
              "[DEBUG] Conversion returned null for dataUri index",
              idx
            );
          }
        });
      } else {
        console.log("[DEBUG] No images found in rawContent.");
      }

      // Build botMessage with images array
      const botMessage = {
        id: Date.now() + 1,
        type: "bot",
        text: sanitizedText || "Response received",
        time: new Date().toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        }),
        error: false,
        images: imagesBlobUrls,
      };

      console.log(
        "[DEBUG] Adding bot message to chat with images count:",
        imagesBlobUrls.length
      );

      setMessages((prev) => [...prev, botMessage]);
    } catch (err) {
      console.error("Error sending message:", err);

      let errorMessage = "Failed to send message. Please try again.";
      if (err.response) {
        errorMessage = err.response.data || err.response.data || errorMessage;
      } else if (err.request) {
        errorMessage = "Network error. Please check your connection.";
      } else if (err.message) {
        errorMessage = err.message;
      }

      // Add error message to chat
      const errorMsg = {
        id: Date.now() + 1,
        type: "bot",
        text: errorMessage,
        time: new Date().toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        }),
        error: true,
        images: [],
      };

      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(e);
    }
  };

  return (
    <>
      <div className="language-selector-fixed">
        <LanguageSelector />
      </div>
      <div className="chat-messages-area">
        <div className="chat-messages-container">
          {/* Render all messages */}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`chat-message-wrapper ${
                msg.type === "user"
                  ? "user-message-wrapper"
                  : "bot-message-wrapper"
              }`}
            >
              <div
                className={`chat-message-content-box ${
                  msg.type === "user" ? "user-message-box" : "bot-message-box"
                }`}
              >
                <div
                  className="rounded-3 p-3"
                  style={{
                    background: msg.error
                      ? "#fee"
                      : msg.type === "user"
                      ? "#E3F2FD"
                      : "#ffffff",
                    border: msg.error ? "1px solid #fcc" : "none",
                    boxShadow: "none",
                  }}
                >
                  {msg.error && (
                    <div className="d-flex align-items-center mb-2">
                      <FiAlertCircle
                        style={{ color: "#dc3545", marginRight: "8px" }}
                      />
                      <strong style={{ color: "#dc3545" }}>Error</strong>
                    </div>
                  )}
                  <div className="mb-2" style={{ color: "#222", fontSize: 16 }}>
                    {/* Render text and images using our renderer (with debug) */}
                    {renderMessageContent(msg)}
                  </div>
                  <hr
                    style={{ borderTop: "1px solid #E9E9EB", margin: "8px 0" }}
                  />
                  <div
                    className={`text-muted small ${
                      msg.type === "user" ? "text-end" : ""
                    }`}
                    style={{ fontSize: 14 }}
                  >
                    {msg.time}
                  </div>
                </div>
              </div>
            </div>
          ))}

          {/* Loading indicator */}
          {loading && (
            <div className="chat-message-wrapper bot-message-wrapper">
              <div className="chat-message-content-box bot-message-box">
                <div
                  className="rounded-3 p-3"
                  style={{
                    background: "#ffffff",
                    border: "none",
                    boxShadow: "none",
                  }}
                >
                  <div
                    className="d-flex align-items-center"
                    style={{ color: "#222", fontSize: 16 }}
                  >
                    <Spinner
                      animation="border"
                      size="sm"
                      role="status"
                      className="me-2"
                    />
                    Thinking...
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Scroll anchor */}
          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="chat-input-container">
        <div className="chat-input-row">
          <Form
            style={{ width: "100%", display: "flex", alignItems: "center" }}
            onSubmit={handleSendMessage}
          >
            {/* Input group containing all icons and input */}
            <InputGroup
              className="chat-input-group"
              style={{
                flex: 1,
                borderRadius: 32,
                boxShadow: "none",
                padding: "0",
                alignItems: "center",
                display: "flex",
                height: "auto",
              }}
            >
              {/* Paperclip icon */}
              <InputGroup.Text
                className="bg-transparent border-0 chat-input-icons"
                style={{
                  paddingLeft: 16,
                  paddingRight: 8,
                  background: "transparent",
                  border: "none",
                }}
              >
                <img src={attach} alt="attach" width={24} height={24} />
              </InputGroup.Text>

              {/* Text Input */}
              <Form.Control
                as="textarea"
                rows={1}
                ref={textareaRef}
                value={message}
                placeholder="Type your message here..."
                className="border-0 bg-transparent chat-input-textarea"
                style={{
                  fontSize: 16,
                  background: "#F8F9FB",
                  boxShadow: "none",
                  borderRadius: 32,
                  height: "56px",
                  minHeight: "56px",
                  maxHeight: "56px",
                  resize: "none",
                  overflow: "auto",
                  padding: "15px 8px",
                  flex: 1,
                }}
                onChange={handleInput}
                onKeyPress={handleKeyPress}
                disabled={loading}
              />

              {/* Mic and Send icons */}
              <InputGroup.Text
                className="bg-transparent border-0 chat-input-icons chat-send-voice"
                style={{
                  paddingLeft: 8,
                  paddingRight: 8,
                  background: "transparent",
                  border: "none",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <img
                  src={mic}
                  alt="mic"
                  width={24}
                  height={24}
                  style={{ marginRight: "16px" }}
                />
                <img
                  src={send_voice}
                  alt="send voice"
                  width={24}
                  height={24}
                  style={{ marginRight: "16px" }}
                />
                <img
                  src={send}
                  alt="send message"
                  width={32}
                  height={32}
                  className={message.trim() && !loading ? "chat-send-icon" : ""}
                  style={{
                    marginRight: "8px",
                    cursor:
                      message.trim() && !loading ? "pointer" : "not-allowed",
                    opacity: message.trim() && !loading ? 1 : 0.5,
                  }}
                  onClick={
                    message.trim() && !loading ? handleSendMessage : undefined
                  }
                />
              </InputGroup.Text>
            </InputGroup>
          </Form>
        </div>
      </div>
    </>
  );
}
export default ChatWindow;
