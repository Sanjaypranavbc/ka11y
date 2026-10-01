import React, { useState, useEffect } from "react";
import {
  Container,
  Row,
  Col,
  Dropdown,
  Spinner,
  Toast,
  ToastContainer,
} from "react-bootstrap";
import { useNavigate } from "react-router-dom";
import { FiChevronDown } from "react-icons/fi";
import { useLanguage } from "../Components/LanguageSelector";
import { getTranslation } from "../utils/translations";
import axiosInstance from "../utils/axios";
import chatIcon from "../assets/icons/chat-Icon-set.png";

const ChatHeader = () => {
  const { language } = useLanguage();
  const navigate = useNavigate();
  const [chatTitle, setChatTitle] = useState("BS9000 Assistant");
  const [tone, setTone] = useState(() => {
    // Initialize from sessionStorage or default to "Friendly"
    const savedPref = sessionStorage.getItem("prefText");
    return savedPref || "Friendly";
  });
  const [updatingPersona, setUpdatingPersona] = useState(false);
  const [toast, setToast] = useState({ show: false, message: "", type: "" });

  // Persona options with value (for API) and label key (for translation)
  const personaOptions = [
    { value: "Friendly", labelKey: "personaSettings.friendly" },
    { value: "Professional", labelKey: "personaSettings.professional" },
    { value: "Casual", labelKey: "personaSettings.casual" },
    { value: "Technical", labelKey: "personaSettings.technical" },
  ];

  // Load chat title from sessionStorage on mount
  useEffect(() => {
    const collectionName = sessionStorage.getItem("chatCollectionName");
    if (collectionName) {
      setChatTitle(collectionName);
    }
  }, []);

  // Handle logo click to navigate to home page
  const handleLogoClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log("Logo clicked, navigating to dashboard");
    navigate("/dashboard");
  };

  const handlePersonaChange = async (selectedPersona) => {
    setTone(selectedPersona);

    try {
      setUpdatingPersona(true);

      // Get user data from localStorage
      const userDataString = localStorage.getItem("token");
      if (!userDataString) {
        throw new Error("User not logged in. Please login again.");
      }

      const userData = JSON.parse(userDataString);
      const { user_id } = userData;

      // Make POST request to edit persona API
      const response = await axiosInstance.post(`/users/${user_id}/persona`, {
        user_id: user_id,
        doc_id: "string",
        persona: selectedPersona,
        thread_id: "",
      });

      console.log("Persona updated:", response.data);

      // Save preference to sessionStorage
      sessionStorage.setItem("prefText", selectedPersona);

      // Show success toast
      setToast({
        show: true,
        message: `Persona changed to ${selectedPersona}`,
        type: "success",
      });
    } catch (err) {
      console.error("Error updating persona:", err);
      // Revert the tone state on error
      const savedPref = sessionStorage.getItem("prefText") || "Friendly";
      setTone(savedPref);

      let errorMessage = "Failed to update persona. Please try again.";
      if (err.response) {
        errorMessage =
          err.response.data?.message || err.response.data || errorMessage;
      } else if (err.message) {
        errorMessage = err.message;
      }

      // Show error toast
      setToast({
        show: true,
        message: errorMessage,
        type: "danger",
      });
    } finally {
      setUpdatingPersona(false);
    }
  };

  return (
    <Container className="body-container">
      <Row className="mb-3 align-items-center chat-header-row">
        <Col>
          <div className="d-flex align-items-center justify-content-between chat-header-info">
            <div className="d-flex align-items-center">
              <div
                className="d-inline-flex align-items-center justify-content-center bg-light rounded p-2 me-3 chat-header-icon"
                style={{
                  width: 54,
                  height: 54,
                  cursor: "pointer",
                  position: "relative",
                  zIndex: 10,
                  pointerEvents: "auto",
                }}
                onClick={handleLogoClick}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    handleLogoClick(e);
                  }
                }}
              >
                <img
                  src={chatIcon}
                  alt="chat icon"
                  width={54}
                  height={54}
                  style={{ pointerEvents: "none" }}
                />
              </div>
              <div className="chat-header-text">
                <div
                  className="fw-semibold chat-header-title"
                  style={{ fontSize: "24px" }}
                >
                  {chatTitle}
                </div>
                <div className="text-muted small chat-header-subtitle">
                  {getTranslation(language, "voice.subtitle")}
                </div>
              </div>
            </div>
          </div>
        </Col>
      </Row>

      <hr style={{ borderTop: "1px solid #E9E9EB", margin: "16px 0" }} />

      {/* Toast Notification */}
      <ToastContainer
        position="top-end"
        className="p-3"
        style={{ zIndex: 9999 }}
      >
        <Toast
          show={toast.show}
          onClose={() => setToast({ ...toast, show: false })}
          delay={3000}
          autohide
          bg={toast.type}
        >
          <Toast.Header>
            <strong className="me-auto">
              {toast.type === "success" ? "Success" : "Error"}
            </strong>
          </Toast.Header>
          <Toast.Body
            className={toast.type === "success" ? "text-white" : "text-white"}
          >
            {toast.message}
          </Toast.Body>
        </Toast>
      </ToastContainer>
    </Container>
  );
};

export default ChatHeader;
