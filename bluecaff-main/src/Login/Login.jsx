import React, { useState, useEffect } from "react";
import {
  Button,
  Form,
  InputGroup,
  Row,
  Col,
  Card,
  Alert,
  Spinner,
} from "react-bootstrap";
import { FiX, FiArrowRight } from "react-icons/fi";
import userIcon from "../assets/icons/user.png";
import keyIcon from "../assets/icons/key.png";
import googleIcon from "../assets/icons/ri_google-fill.png";
import lockIcon from "../assets/icons/lock.svg";
import "./login.css";
import { useNavigate } from "react-router-dom";
import LanguageSelector, { useLanguage } from "../Components/LanguageSelector";
import { getTranslation } from "../utils/translations";
import axiosInstance from "../utils/axios";

function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { language } = useLanguage();
  const navigate = useNavigate();

  // Check if user is already logged in
  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      // If token exists, redirect to dashboard
      navigate("/dashboard", { replace: true });
    }
  }, [navigate]);

  // Set default login credentials on component mount

  const clearEmail = () => setEmail("");
  const clearPassword = () => setPassword("");

  const onSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await axiosInstance.post("/login", {
        user_mail_id: email,
        password: password,
      });

      console.log("====================================");
      console.log(response, "response");
      console.log("====================================");

      // Check if login was successful
      if (response.data) {
        localStorage.setItem("token", JSON.stringify(response.data));

        // Clear any chat session data on login
        sessionStorage.removeItem("chatCollectionName");
        sessionStorage.removeItem("chatUserId");
        sessionStorage.removeItem("chatThreadId");

        // Navigate to dashboard on success
        navigate("/dashboard");
      }
    } catch (err) {
      // Handle errors
      if (err.response) {
        // Server responded with error
        setError(
          err.response.data.message ||
            "Login failed. Please check your credentials."
        );
      } else if (err.request) {
        // Request made but no response
        setError("Network error. Please check your connection.");
      } else {
        // Other errors
        setError("An error occurred. Please try again.");
      }
      console.error("Login error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      {/* Language Selector - Fixed Position */}
      <div className="language-selector-fixed">
        <LanguageSelector />
      </div>

      <Row className="h-100 g-0">
        {/* Left Grid - Background Image */}
        <Col md={6} className="login-left-grid">
          <div className="login-background-section"></div>
        </Col>

        {/* Right Grid - Login Form */}
        <Col md={6} className="login-right-grid">
          <div className="login-form-container">
            <Card className="login-form-card shadow">
              <Card.Body className="p-4 p-md-5">
                <div className="text-center mb-4">
                  <h5 className="mb-1">
                    {getTranslation(language, "login.welcomeBack")}
                  </h5>
                  <div className="text-muted">
                    {getTranslation(language, "login.subtitle")}
                  </div>
                </div>

                {/* Error Alert */}
                {error && (
                  <Alert
                    variant="danger"
                    onClose={() => setError("")}
                    dismissible
                  >
                    {error}
                  </Alert>
                )}

                <Form onSubmit={onSubmit}>
                  <Form.Group className="mb-3" controlId="loginEmail">
                    <Form.Label>
                      {getTranslation(language, "login.email")}
                    </Form.Label>
                    <InputGroup>
                      <InputGroup.Text>
                        <img src={userIcon} alt="User" width={16} height={16} />
                      </InputGroup.Text>
                      <Form.Control
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                      />
                      <Button
                        variant="outline-secondary"
                        onClick={clearEmail}
                        aria-label="Clear email"
                      >
                        <FiX />
                      </Button>
                    </InputGroup>
                  </Form.Group>

                  <Form.Group className="mb-3" controlId="loginPassword">
                    <Form.Label>
                      {getTranslation(language, "login.password")}
                    </Form.Label>
                    <InputGroup>
                      <InputGroup.Text>
                        <img src={keyIcon} alt="User" width={16} height={16} />
                      </InputGroup.Text>
                      <Form.Control
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                      />
                      <Button
                        variant="outline-secondary"
                        onClick={clearPassword}
                        aria-label="Clear password"
                      >
                        <FiX />
                      </Button>
                    </InputGroup>
                  </Form.Group>

                  <div className="d-grid mt-2">
                    <Button
                      variant="dark"
                      type="submit"
                      className="py-2"
                      disabled={loading}
                    >
                      {loading ? (
                        <>
                          <Spinner
                            as="span"
                            animation="border"
                            size="sm"
                            role="status"
                            aria-hidden="true"
                            className="me-2"
                          />
                          Logging in...
                        </>
                      ) : (
                        <>
                          <span className="me-2">
                            <img
                              src={lockIcon}
                              alt="User"
                              width={16}
                              height={16}
                            />
                          </span>
                          {getTranslation(language, "login.loginButton")}
                          <span className="ms-2">
                            <FiArrowRight />
                          </span>
                        </>
                      )}
                    </Button>
                  </div>
                </Form>

                {/* <div className="d-flex align-items-center text-muted my-4">
                  <div
                    className="flex-grow-1"
                    style={{ height: 1, background: "#e9ecef" }}
                  />
                  <span className="px-3">
                    {getTranslation(language, "login.orText")}
                  </span>
                  <div
                    className="flex-grow-1"
                    style={{ height: 1, background: "#e9ecef" }}
                  />
                </div> */}

                {/* <div className="d-grid">
                  <Button
                    variant="light"
                    className="py-2 border"
                    onClick={() => navigate("/dashboard")}
                  >
                    <span className="me-2">
                      <img src={googleIcon} alt="User" width={16} height={16} />
                    </span>
                    {getTranslation(language, "login.googleLogin")}
                  </Button>
                </div> */}
              </Card.Body>
            </Card>
          </div>
        </Col>
      </Row>
    </div>
  );
}

export default Login;
