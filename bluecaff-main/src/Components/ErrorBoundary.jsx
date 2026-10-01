import React, { Component } from "react";
import { Toast, ToastContainer } from "react-bootstrap";

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      showToast: false,
    };
  }

  static getDerivedStateFromError(error) {
    // Update state so the next render will show the toast
    return { hasError: true, showToast: true };
  }

  componentDidCatch(error, errorInfo) {
    // Log error details for debugging
    console.error("Uncaught error:", error, errorInfo);

    this.setState({
      error,
      errorInfo,
      showToast: true,
    });

    // You can also log the error to an error reporting service here
    // logErrorToService(error, errorInfo);
  }

  handleCloseToast = () => {
    this.setState({ showToast: false, hasError: false });
  };

  render() {
    const errorMessage =
      this.state.error?.message || "An unexpected error occurred";

    return (
      <>
        {/* Toast Notification for Error */}
        <ToastContainer
          position="top-end"
          className="p-3"
          style={{ zIndex: 9999 }}
        >
          <Toast
            show={this.state.showToast}
            onClose={this.handleCloseToast}
            delay={5000}
            autohide
            bg="danger"
          >
            <Toast.Header>
              <strong className="me-auto">Error</strong>
            </Toast.Header>
            <Toast.Body className="text-white">{errorMessage}</Toast.Body>
          </Toast>
        </ToastContainer>

        {/* Render children normally */}
        {this.props.children}
      </>
    );
  }
}

export default ErrorBoundary;
