import React, { useState, useEffect } from "react";
import {
  Container,
  Button,
  Card,
  Form,
  InputGroup,
  Spinner,
  Alert,
  Toast,
  ToastContainer,
} from "react-bootstrap";
import { FiSearch } from "react-icons/fi";
import LanguageSelector, { useLanguage } from "../Components/LanguageSelector";
import Sidebar from "../Components/Header";
import { getTranslation } from "../utils/translations";
import axiosInstance from "../utils/axios";
import "./ProductList.css";
import addProductIcon from "../assets/images/plusIcon.png";
import addProuctListIcon from "../assets/icons/add-products-icon.png";

function ProductList() {
  const { language } = useLanguage();
  const [searchTerm, setSearchTerm] = useState("");
  const [sortBy, setSortBy] = useState("All");
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // const [currentLanguage, setCurrentLanguage] = useState(language);
  const [mappingDocId, setMappingDocId] = useState(null);
  const [toast, setToast] = useState({ show: false, message: "", type: "" });

  const fetchProducts = async (languageFilter = null) => {
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
      const { user_id } = userData;

      // Build params object
      const params = {
        user_id: user_id,
      };

      // Add language filter if not "All"
      if (languageFilter && languageFilter !== "All") {
        params.language = languageFilter;
      }

      // Make GET request with user_id and optional language filter
      const response = await axiosInstance.get(
        `/users/${user_id}/documents/unmapped`,
        {
          params: params,
        }
      );

      // Set products from unmapped_documents array
      if (response.data && response.data.unmapped_documents) {
        setProducts(response.data.unmapped_documents);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleChatWithProduct = async (docId) => {
    try {
      setMappingDocId(docId);
      setError("");
      setToast({ show: false, message: "", type: "" });

      // Get user data from localStorage
      const userDataString = localStorage.getItem("token");
      if (!userDataString) {
        setError("User not logged in. Please login again.");
        return;
      }

      const userData = JSON.parse(userDataString);
      const { user_id } = userData;

      // Make POST request to map document to user
      const response = await axiosInstance.post(
        `/users/${user_id}/documents/${docId}`,
        {
          user_id: user_id,
          doc_id: docId,
          collection_name: "",
        }
      );

      // Remove the added product from the list immediately without reloading
      setProducts((prevProducts) =>
        prevProducts.filter((product) => product.doc_id !== docId)
      );

      // Show success toast
      const message = response.data?.message || "Document mapped successfully!";
      setToast({ show: true, message: message, type: "success" });
    } catch (err) {
      console.error("Error mapping document:", err);
      let errorMessage = "Failed to map document. Please try again.";
      if (err.response) {
        errorMessage =
          err.response.data.message || err.response.data.detail || errorMessage;
      } else if (err.request) {
        errorMessage = "Network error. Please check your connection.";
      }
      setToast({ show: true, message: errorMessage, type: "danger" });
    } finally {
      setMappingDocId(null);
    }
  };

  // Handle sort/language filter change
  const handleSortChange = (value) => {
    setSortBy(value);
    fetchProducts(value);
  };

  // Filter products by search term only (language filtering is done via API)
  const filteredProducts = products.filter((product) => {
    const matchesSearch =
      product.doc_topic?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      product.description?.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesSearch;
  });

  return (
    <div className="product-list-layout">
      {/* Sidebar Navigation */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="main-content">
        <div className="product-list-page">
          {/* Language Selector - Fixed Position */}
          <div className="language-selector-fixed">
            <LanguageSelector />
          </div>

          <Container fluid className="product-list-container">
            {/* Header Section */}
            <div className="product-list-header">
              <div className="header-content">
                <div className="header-left">
                  <div className="header-icon">
                    <img
                      src={addProductIcon}
                      alt="Add Product"
                      width={54}
                      height={54}
                    />
                  </div>
                  <div className="header-text">
                    <h1 className="page-title">
                      {getTranslation(language, "productList.pageTitle")}
                    </h1>
                    <p className="page-subtitle">
                      {getTranslation(language, "productList.pageSubtitle")}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Divider Line */}
            <div className="header-divider"></div>

            {/* Products Section */}
            <div className="products-section">
              <div className="products-header">
                <h2 className="products-title">
                  {getTranslation(language, "productList.productsTitle")}
                </h2>

                <div className="products-controls">
                  {/* Sort Dropdown */}
                  <div className="sort-control">
                    <label className="control-label">
                      {getTranslation(language, "productList.sortLabel")}
                    </label>
                    <Form.Select
                      value={sortBy}
                      onChange={(e) => handleSortChange(e.target.value)}
                      className="sort-select"
                    >
                      <option value="All">
                        {getTranslation(language, "productList.sortAll")}
                      </option>
                      <option value="en">EN</option>
                      <option value="jp">JA</option>
                    </Form.Select>
                  </div>

                  {/* Search Box */}
                  <div className="search-control">
                    <InputGroup className="search-input-group">
                      <InputGroup.Text className="search-icon">
                        <FiSearch size={16} />
                      </InputGroup.Text>
                      <Form.Control
                        type="text"
                        placeholder={getTranslation(
                          language,
                          "productList.searchPlaceholder"
                        )}
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="search-input"
                      />
                    </InputGroup>
                  </div>
                </div>
              </div>

              {/* Loading State */}
              {loading && (
                <div className="text-center py-5">
                  <Spinner animation="border" role="status" variant="primary">
                    <span className="visually-hidden">Loading...</span>
                  </Spinner>
                  <div className="mt-3 text-muted">Loading products...</div>
                </div>
              )}

              {/* Error State */}
              {error && !loading && (
                <Alert
                  variant="danger"
                  onClose={() => setError("")}
                  dismissible
                >
                  {error}
                  <div className="mt-2">
                    <Button
                      variant="outline-danger"
                      size="sm"
                      onClick={fetchProducts}
                    >
                      Retry
                    </Button>
                  </div>
                </Alert>
              )}

              {/* Products Grid */}
              {!loading && !error && (
                <>
                  {filteredProducts.length === 0 ? (
                    <div className="text-center py-5">
                      <div className="text-muted mb-3">No products found</div>
                      <Button variant="primary" onClick={fetchProducts}>
                        Refresh
                      </Button>
                    </div>
                  ) : (
                    <div className="products-grid">
                      {filteredProducts.map((product) => (
                        <Card key={product.doc_id} className="product-card">
                          <Card.Body className="product-card-body">
                            <div className="product-content">
                              <div className="product-image">
                                <img
                                  src="https://placehold.co/80x80/e3f2fd/2563eb?text=Product&font=roboto"
                                  alt={product.doc_topic}
                                  className="product-img"
                                />
                              </div>

                              <div className="product-details">
                                <h3 className="product-name">
                                  {product.doc_topic}
                                </h3>
                                <p className="product-description">
                                  {product.description}
                                </p>
                              </div>

                              <div className="product-actions">
                                <Button
                                  variant="dark"
                                  className="chat-button"
                                  onClick={() =>
                                    handleChatWithProduct(product.doc_id)
                                  }
                                  disabled={mappingDocId === product.doc_id}
                                >
                                  {mappingDocId === product.doc_id ? (
                                    <>
                                      <Spinner
                                        as="span"
                                        animation="border"
                                        size="sm"
                                        role="status"
                                        aria-hidden="true"
                                      />
                                    </>
                                  ) : (
                                    <img src={addProuctListIcon} alt="Chat" />
                                  )}
                                </Button>
                              </div>
                            </div>
                          </Card.Body>
                        </Card>
                      ))}
                    </div>
                  )}
                </>
              )}

              {/* Add Product Button - After Product List */}
              {/* <div className="add-product-section">
                <Button
                  className="add-product-button"
                  variant="dark"
                  onClick={handleAddProduct}
                >
                  <FiPlus className="me-2" size={18} />
                  {getTranslation(language, "productList.addProductButton")}
                </Button>
              </div> */}
            </div>
          </Container>
        </div>
      </div>

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
          <Toast.Body className="text-white">{toast.message}</Toast.Body>
        </Toast>
      </ToastContainer>
    </div>
  );
}

export default ProductList;
