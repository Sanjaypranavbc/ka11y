import React, { useState, useEffect } from "react";
import {
  Container,
  Row,
  Col,
  Button,
  Card,
  Spinner,
  Alert,
  Toast,
  ToastContainer,
} from "react-bootstrap";
import { FiPlus, FiTrash2, FiEye, FiPhone } from "react-icons/fi";
import chatIcon from "../assets/icons/chat-Icon-set.png";
import LanguageSelector, { useLanguage } from "../Components/LanguageSelector";
import { getTranslation } from "../utils/translations";
import axiosInstance from "../utils/axios";
import { useNavigate } from "react-router-dom";

function DashboardData() {
  const { language } = useLanguage();
  const navigate = useNavigate();
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingDocId, setDeletingDocId] = useState(null);
  const [chattingDocId, setChattingDocId] = useState(null);
  const [initializingChat, setInitializingChat] = useState(false);
  const [viewingPdfId, setViewingPdfId] = useState(null);
  const [toast, setToast] = useState({ show: false, message: "", type: "" });

  const fetchProducts = async () => {
    console.log("Fetching products...");

    try {
      setLoading(true);
      setError("");

      // Get user data from localStorage
      const userDataString = localStorage.getItem("token");
      if (!userDataString) {
        setError("User not logged in. Please login again.");
        setLoading(false);
        return;
      }

      const userData = JSON.parse(userDataString);
      const { user_id, username } = userData;

      // Make GET request with user_id and username as query parameters
      const response = await axiosInstance.get(`/users/${user_id}/documents`, {
        params: {
          user_name: username,
        },
      });

      // Set products from documents array
      if (response.data && response.data.documents) {
        setProducts(response.data.documents);
      } else {
        setProducts([]);
      }
    } catch (err) {
      console.error("Error fetching products:", err);
      if (err.response) {
        setError(
          err.response.data.message ||
            "Failed to fetch products. Please try again."
        );
      } else if (err.request) {
        setError("Network error. Please check your connection.");
      } else {
        setError("An error occurred. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  // Fetch products from API on component mount
  useEffect(() => {
    fetchProducts();

    // Set default persona to "Friendly" in sessionStorage if not already set
    const savedPref = sessionStorage.getItem("prefText");
    if (!savedPref) {
      sessionStorage.setItem("prefText", "Friendly");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDelete = async (docId) => {
    try {
      setDeletingDocId(docId);

      // Get user data from localStorage
      const userDataString = localStorage.getItem("token");
      if (!userDataString) {
        setToast({
          show: true,
          message: "User not logged in. Please login again.",
          type: "danger",
        });
        return;
      }

      const userData = JSON.parse(userDataString);
      const { user_id } = userData;

      // Make DELETE request to unmap document from user
      const response = await axiosInstance.get(
        `/users/${user_id}/documents/${docId}/unmap`,
        {
          data: {
            user_id: user_id,
            doc_id: docId,
            collection_name: "your_collection_name", // Update this with actual collection name if needed
          },
        }
      );

      // Show success toast
      setToast({
        show: true,
        message: response.data.message || "Document removed successfully!",
        type: "success",
      });

      // Refresh the products list after successful deletion
      fetchProducts();
    } catch (err) {
      console.error("Error deleting document:", err);
      let errorMessage = "Failed to delete document. Please try again.";

      if (err.response) {
        errorMessage =
          err.response.data.message || err.response.data.detail || errorMessage;
      } else if (err.request) {
        errorMessage = "Network error. Please check your connection.";
      }

      // Show error toast
      setToast({
        show: true,
        message: errorMessage,
        type: "danger",
      });
    } finally {
      setDeletingDocId(null);
    }
  };

  const handleFloatingButtonClick = () => {
    // Navigate to products page
    navigate("/products");
  };

  const handleChatWithAssistant = async (docId) => {
    try {
      setChattingDocId(docId);
      setInitializingChat(true);

      const userDataString = localStorage.getItem("token");
      if (!userDataString) {
        setToast({
          show: true,
          message: "User not logged in. Please login again.",
          type: "danger",
        });
        navigate("/login", { replace: true });
        return;
      }

      const userData = JSON.parse(userDataString);
      const { user_id } = userData;

      const response = await axiosInstance.post(
        `/users/${user_id}/chat/reinit?doc_id=${docId}`,
        {
          user_id: user_id,
          doc_id: docId,
        }
      );

      // Expecting response to contain collection_name, user_id, thread_id, and pdf_language
      const {
        collection_name,
        user_id: respUserId,
        thread_id,
        pdf_language,
      } = response.data || {};

      if (collection_name) {
        // Persist for chat page consumption
        sessionStorage.setItem("chatCollectionName", collection_name);
      }
      if (respUserId) {
        sessionStorage.setItem("chatUserId", String(respUserId));
      }
      if (thread_id) {
        sessionStorage.setItem("chatThreadId", String(thread_id));
      }
      if (pdf_language) {
        // Save pdf_language as chatLang in sessionStorage
        sessionStorage.setItem("chatLang", pdf_language);
      }

      // Wait a bit to ensure sessionStorage is written before navigation
      // await new Promise((resolve) => setTimeout(resolve, 100));

      // Navigate to chat page
      setTimeout(() => {
        navigate("/chat");
      }, 600);
    } catch (err) {
      console.error("Error initializing chat:", err);
      let errorMessage = "Failed to start chat. Please try again.";
      if (err.response) {
        errorMessage =
          err.response.data?.message || err.response.data || errorMessage;
      } else if (err.request) {
        errorMessage = "Network error. Please check your connection.";
      }
      setToast({ show: true, message: errorMessage, type: "danger" });
    } finally {
      setChattingDocId(null);
      setInitializingChat(false);
    }
  };

  const handleVoiceWithAssistant = async (docId) => {
    setChattingDocId(docId);
    setInitializingChat(true);

    const userDataString = localStorage.getItem("token");
    if (!userDataString) {
      setToast({
        show: true,
        message: "User not logged in. Please login again.",
        type: "danger",
      });
      navigate("/login", { replace: true });
      return;
    }

    const userData = JSON.parse(userDataString);
    const { user_id } = userData;

    sessionStorage.setItem("chatUserId", String(user_id));
    sessionStorage.setItem("chatCollectionName", docId);

    navigate("/voice");
    setChattingDocId(null);
    setInitializingChat(false);
  };

  const handleViewPdf = async (docId) => {
    try {
      setViewingPdfId(docId);

      const response = await axiosInstance.get(`/get-pdf-url/${docId}`);

      if (response.data && response.data.url) {
        // Open PDF in new tab
        window.open(response.data.url, "_blank");
      } else {
        setToast({
          show: true,
          message: "PDF URL not found",
          type: "danger",
        });
      }
    } catch (err) {
      console.error("Error getting PDF URL:", err);
      let errorMessage = "Failed to get PDF URL. Please try again.";
      if (err.response) {
        errorMessage =
          err.response.data?.message || err.response.data || errorMessage;
      } else if (err.request) {
        errorMessage = "Network error. Please check your connection.";
      }
      setToast({ show: true, message: errorMessage, type: "danger" });
    } finally {
      setViewingPdfId(null);
    }
  };

  return (
    <>
      {/* Full-Screen Loading Overlay */}
      {initializingChat && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0, 0, 0, 0.7)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
        >
          <Spinner
            animation="border"
            role="status"
            variant="light"
            style={{ width: "4rem", height: "4rem" }}
          >
            <span className="visually-hidden">Loading...</span>
          </Spinner>
          <div className="mt-4 text-white" style={{ fontSize: "1.2rem" }}>
            Initializing chat session...
          </div>
        </div>
      )}

      {/* Language Selector - Fixed Position */}
      <div className="language-selector-fixed">
        <LanguageSelector />
      </div>

      <Container className="body-container">
        <div className="mb-4">
          <h4 className="mb-2" style={{ fontWeight: 800 }}>
            {getTranslation(language, "dashboard.title")}
          </h4>
          <div className="text-muted">
            {getTranslation(language, "dashboard.description")}
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="text-center py-5">
            <Spinner animation="border" role="status" variant="primary">
              <span className="visually-hidden">Loading...</span>
            </Spinner>
            <div className="mt-3 text-muted">
              {getTranslation(language, "dashboard.loadingProducts")}
            </div>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <Alert variant="danger" onClose={() => setError("")} dismissible>
            {error}
            <div className="mt-2">
              <Button
                variant="outline-danger"
                size="sm"
                onClick={fetchProducts}
              >
                {getTranslation(language, "dashboard.retryButton")}
              </Button>
            </div>
          </Alert>
        )}

        {/* Products Grid */}
        {!loading && !error && (
          <>
            {products.length === 0 ? (
              <div className="text-center py-5">
                <div className="text-muted mb-3">
                  {getTranslation(language, "dashboard.noProductsFound")}
                </div>
                <Button variant="primary" onClick={fetchProducts}>
                  {getTranslation(language, "dashboard.refreshButton")}
                </Button>
              </div>
            ) : (
              <Row className="g-4">
                {products.map((p) => (
                  <Col key={p.doc_id} xs={12} md={6} lg={4}>
                    <Card className="border-0 h-100 position-relative">
                      {/* Delete Icon */}
                      {/* <Button
                        variant="link"
                        className="position-absolute top-0 end-0 m-2 p-0 text-danger chat-card-delete-btn"
                        style={{
                          zIndex: 10,
                          width: "32px",
                          height: "32px",
                          borderRadius: "50%",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                        onClick={() => handleDelete(p.doc_id)}
                        disabled={deletingDocId === p.doc_id}
                        aria-label={`${getTranslation(
                          language,
                          "dashboard.deleteAria"
                        )} ${p.doc_topic}`}
                      >
                        {deletingDocId === p.doc_id ? (
                          <Spinner
                            as="span"
                            animation="border"
                            size="sm"
                            role="status"
                            aria-hidden="true"
                          />
                        ) : (
                          <FiTrash2 size={14} />
                        )}
                      </Button> */}

                      <Card.Body className="d-flex flex-column chatCards">
                        <div className="position-relative">
                          <div className="d-flex align-items-start justify-content-between bg-light rounded mb-3 ">
                            <img
                              src={chatIcon}
                              alt="chat icon"
                              width={54}
                              height={54}
                            />
                            <div className="d-inline-flex gap-8">
                              {/* Eye Icon */}
                              <Button
                                variant="link"
                                className="m-1 p-0 chat-card-eye-btn"
                                style={{
                                  zIndex: 10,
                                  width: "32px",
                                  height: "32px",
                                  borderRadius: "50%",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                }}
                                onClick={() => handleViewPdf(p.doc_id)}
                                disabled={viewingPdfId === p.doc_id}
                                aria-label={`View PDF for ${p.doc_topic}`}
                                title="View PDF"
                              >
                                {viewingPdfId === p.doc_id ? (
                                  <Spinner
                                    as="span"
                                    animation="border"
                                    size="sm"
                                    role="status"
                                    aria-hidden="true"
                                  />
                                ) : (
                                  <FiEye size={16} />
                                )}
                              </Button>
                              {/* Delete Icon */}
                              <Button
                                variant="link"
                                className="m-1 p-0 chat-card-delete-btn"
                                style={{
                                  zIndex: 10,
                                  width: "32px",
                                  height: "32px",
                                  borderRadius: "50%",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                }}
                                onClick={() => handleDelete(p.doc_id)}
                                disabled={deletingDocId === p.doc_id}
                                aria-label={`${getTranslation(
                                  language,
                                  "dashboard.deleteAria"
                                )} ${p.doc_topic}`}
                                title="Delete PDF"
                              >
                                {deletingDocId === p.doc_id ? (
                                  <Spinner
                                    as="span"
                                    animation="border"
                                    size="sm"
                                    role="status"
                                    aria-hidden="true"
                                  />
                                ) : (
                                  <FiTrash2 size={16} />
                                )}
                              </Button>
                            </div>
                          </div>
                        </div>
                        <h5 className="mb-2">{p.doc_topic}</h5>
                        <div
                          className="text-muted mb-4"
                          style={{ minHeight: 48 }}
                        >
                          {p.description}
                        </div>
                        <div className="mt-auto">
                          <div className="d-flex gap-2">
                            <Button
                              variant="dark"
                              className="flex-grow-1 py-2"
                              onClick={() => handleChatWithAssistant(p.doc_id)}
                              disabled={chattingDocId === p.doc_id}
                            >
                              {chattingDocId === p.doc_id ? (
                                <>
                                  <Spinner
                                    as="span"
                                    animation="border"
                                    size="sm"
                                    role="status"
                                    aria-hidden="true"
                                    className="me-2"
                                  />
                                  {getTranslation(
                                    language,
                                    "dashboard.chatButton"
                                  )}
                                </>
                              ) : (
                                getTranslation(language, "dashboard.chatButton")
                              )}
                            </Button>
                            <Button
                              variant="outline-dark"
                              className="py-2 px-3"
                              onClick={() => handleVoiceWithAssistant(p.doc_id)}
                              disabled={viewingPdfId === p.doc_id}
                              aria-label={`Call for ${p.doc_topic}`}
                              title="Call"
                            >
                              {viewingPdfId === p.doc_id ? (
                                <Spinner
                                  as="span"
                                  animation="border"
                                  size="sm"
                                  role="status"
                                  aria-hidden="true"
                                />
                              ) : (
                                <FiPhone size={16} />
                              )}
                            </Button>
                          </div>
                        </div>
                      </Card.Body>
                    </Card>
                  </Col>
                ))}
              </Row>
            )}
          </>
        )}
      </Container>

      {/* Floating + Button */}
      <Button
        className="floating-add-btn"
        variant="primary"
        onClick={handleFloatingButtonClick}
        aria-label={getTranslation(language, "common.addNewItem")}
      >
        <FiPlus size={24} />
      </Button>

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
    </>
  );
}

export default DashboardData;
