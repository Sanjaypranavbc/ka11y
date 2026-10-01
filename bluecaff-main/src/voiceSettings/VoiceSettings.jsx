import React from "react";
import { Container } from "react-bootstrap";
import LanguageSelector, { useLanguage } from "../Components/LanguageSelector";
import Sidebar from "../Components/Header";
import { getTranslation } from "../utils/translations";
import "./VoiceSettings.css";
import personalHeaderIcon from "../assets/icons/voice-setting-icn.svg";

function VoiceSettings() {
  const { language } = useLanguage();

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="main-content">
        <div className="page-content">
          <Container className="persona-settings-container">
            {/* Language Selector - Fixed Position */}
            <div className="language-selector-fixed">
              <LanguageSelector />
            </div>

            {/* Header Section */}
            <div className="page-header">
              <div className="header-left">
                <div className="header-icon">
                  <img
                    src={personalHeaderIcon}
                    alt="Voice Settings"
                    width={54}
                    height={54}
                  />
                </div>
                <div className="header-text">
                  <h1 className="page-title">
                    {getTranslation(language, "voiceSettings.title") ||
                      "Voice Settings"}
                  </h1>
                  <p className="page-subtitle">
                    {getTranslation(language, "voiceSettings.subtitle") ||
                      "Configure your voice assistant preferences"}
                  </p>
                </div>
              </div>
            </div>

            <div className="header-divider"></div>

            <p>
              {getTranslation(language, "voiceSettings.content") ||
                "We are working on this exciting feature and will be releasing it soon. This will enable any user to speak naturally and communicate with any product manual. Our RAG-powered voice chatbot lets you ask questions, troubleshoot issues, and find specific instructions instantly without interruption. Just tap the mic and get accurate, real-time answers sourced directly from your product's user manual."}
            </p>
          </Container>
        </div>
      </div>
    </div>
  );
}

export default VoiceSettings;
