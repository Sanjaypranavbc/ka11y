import React from "react";
import { Container } from "react-bootstrap";
import LanguageSelector, { useLanguage } from "../Components/LanguageSelector";
import Sidebar from "../Components/Header";
import { getTranslation } from "../utils/translations";
import "./DocUpload.css";
import uploadIcon from "../assets/icons/add-products-icon.png";
import personalHeaderIcon from "../assets/icons/doc-upload-icn.svg";

function DocUpload() {
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
                    alt="Document Upload"
                    width={54}
                    height={54}
                  />
                </div>
                <div className="header-text">
                  <h1 className="page-title">
                    {getTranslation(language, "Doc Upload") ||
                      "Document Upload"}
                  </h1>
                  <p className="page-subtitle">
                    {getTranslation(language, "docUpload.subtitle") ||
                      "Upload your documents for processing"}
                  </p>
                </div>
              </div>
            </div>

            <div className="header-divider"></div>

            <p>
              {getTranslation(language, "docUpload.content") ||
                "This feature is coming soon. Our Doc Upload feature will automatically retrieve your product manuals and digital assets directly from your Resource Manager, Content Management Systems or shared drives and repositories.  Each file is processed through intelligent chunking and smart indexing, converted into high-quality embeddings, and stored in a dedicated vector database for every product. This fully automated pipeline transforms your content into a RAG-ready knowledge system that delivers fast and accurate retrieval at scale."}
            </p>

            {/* Note Section */}
            <div className="note-container">
              <p className="note-text">
                {getTranslation(language, "docUpload.noteText") ||
                  "RAG (Retrieval-Augmented Generation) is an AI technique that combines a language model with a retrieval system. When you ask a question, the system first searches for the most relevant information from trusted documents, then the AI uses that information to generate accurate, context-aware answers. This ensures responses are grounded in real data rather than relying only on the model's memory."}
              </p>
            </div>
          </Container>
        </div>
      </div>
    </div>
  );
}

export default DocUpload;
