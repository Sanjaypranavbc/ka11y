import React, { useState, useEffect } from "react";
import { Nav, Button, Dropdown } from "react-bootstrap";
import { useNavigate, useLocation } from "react-router-dom";
import {
  FiHome,
  FiUpload,
  FiSettings,
  FiPlus,
  FiMoreHorizontal,
  FiLogOut,
  FiMenu,
  FiX,
  FiUser,
} from "react-icons/fi";
import logo from "../assets/logo.svg";
import "./header.css";
import { useLanguage } from "./LanguageSelector";
import { getTranslation } from "../utils/translations";
import LanguageSelector from "./LanguageSelector";

function Sidebar() {
  const [activeItem, setActiveItem] = useState("home");
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [username, setUsername] = useState("User");
  const [userId, setUserId] = useState("");
  const navigate = useNavigate();
  const location = useLocation();
  const { language } = useLanguage();

  // Get username and user_id from token
  useEffect(() => {
    try {
      const token = localStorage.getItem("token");
      if (token) {
        const tokenData = JSON.parse(token);
        setUsername(tokenData.username || "User");
        setUserId(tokenData.user_id || "");
      }
    } catch (error) {
      console.error("Error reading token:", error);
      setUsername("User");
      setUserId("");
    }
  }, []);

  const menuItems = [
    {
      name: getTranslation(language, "sidebar.addProduct"),
      key: "addProduct",
      icon: FiPlus,
      isButton: true,
      path: "/products",
    },
    {
      name: getTranslation(language, "sidebar.home"),
      key: "home",
      icon: FiHome,
      path: "/dashboard",
    },
    {
      name: getTranslation(language, "sidebar.docUpload"),
      key: "docUpload",
      icon: FiUpload,
      path: "/doc-upload",
    },
    {
      name: getTranslation(language, "sidebar.personalitySetting"),
      key: "personalitySetting",
      icon: FiSettings,
      path: "/persona-settings",
    },
    {
      name: getTranslation(language, "sidebar.voiceSettings"),
      key: "voiceSettings",
      icon: FiSettings,
      path: "/voice-settings",
    },
  ];

  // Set active item based on current path
  useEffect(() => {
    const currentPath = location.pathname;
    const activeMenuItem = menuItems.find((item) => item.path === currentPath);
    if (activeMenuItem) {
      setActiveItem(activeMenuItem.key);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const handleNavigation = (item) => {
    setActiveItem(item.key);

    // Clear chat session data when navigating away from chat
    if (item.path !== "/chat") {
      sessionStorage.removeItem("chatCollectionName");
      sessionStorage.removeItem("chatUserId");
      sessionStorage.removeItem("chatThreadId");
      sessionStorage.removeItem("chatLang");
    }

    navigate(item.path);
    if (isMobileOpen) {
      setIsMobileOpen(false); // Close mobile menu after navigation
    }
  };

  const toggleMobileSidebar = () => {
    setIsMobileOpen(!isMobileOpen);
  };

  const handleLogout = () => {
    console.log("Logging out...");

    // Clear all localStorage
    localStorage.clear();

    // Clear all sessionStorage
    sessionStorage.clear();

    // Navigate to login page
    navigate("/login");

    // Close mobile menu if open
    if (isMobileOpen) {
      setIsMobileOpen(false);
    }
  };

  return (
    <>
      {/* Mobile Header Bar */}
      <div className="mobile-header d-md-none">
        <div className="mobile-header-content">
          <img
            src={logo}
            alt="blue caffeine"
            width={120}
            height={44}
            className="mobile-logo"
            onClick={() => navigate("/dashboard")}
            style={{ cursor: "pointer" }}
          />
          <Button
            className="mobile-menu-toggle"
            variant="link"
            onClick={toggleMobileSidebar}
          >
            <FiMenu size={24} />
          </Button>
        </div>
      </div>

      {/* Mobile Full-Width Menu Overlay */}
      {isMobileOpen && (
        <div className="mobile-menu-overlay d-md-none">
          <div className="mobile-menu-content">
            {/* Mobile Menu Header */}
            <div className="mobile-menu-header">
              <img
                src={logo}
                alt="blue caffeine"
                width={120}
                height={44}
                className="mobile-menu-logo"
                onClick={() => {
                  navigate("/dashboard");
                  setIsMobileOpen(false);
                }}
                style={{ cursor: "pointer" }}
              />
              <Button
                className="mobile-menu-close"
                variant="link"
                onClick={() => setIsMobileOpen(false)}
              >
                <FiX size={24} />
              </Button>
            </div>

            {/* Mobile Menu Items */}
            <div className="mobile-menu-items">
              {menuItems.map((item) => (
                <div key={item.key} className="mobile-menu-item">
                  {item.isButton ? (
                    <Button
                      variant="primary"
                      className="mobile-add-btn w-100"
                      onClick={() => handleNavigation(item)}
                    >
                      <item.icon className="me-2" size={18} />
                      {item.name}
                    </Button>
                  ) : (
                    <button
                      className={`mobile-nav-item ${
                        activeItem === item.key ? "active" : ""
                      }`}
                      onClick={() => handleNavigation(item)}
                    >
                      <item.icon className="mobile-nav-icon" size={20} />
                      <span className="mobile-nav-text">{item.name}</span>
                    </button>
                  )}
                </div>
              ))}
            </div>

            {/* Mobile Language Selector */}
            <div className="mobile-language-section">
              <LanguageSelector />
            </div>

            {/* Mobile Profile Section */}
            <div className="mobile-profile-section">
              <div className="mobile-profile-info">
                <div className="mobile-profile-avatar-icon">
                  <FiUser size={24} />
                </div>
                <div className="mobile-profile-details">
                  <div className="mobile-profile-name">{username}</div>
                  {userId && (
                    <div className="mobile-profile-id">ID: {userId}</div>
                  )}
                </div>
              </div>
              <Button
                className="mobile-logout-btn"
                variant="outline-danger"
                onClick={handleLogout}
              >
                <FiLogOut className="me-2" size={16} />
                {getTranslation(language, "sidebar.logout")}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Desktop Sidebar */}
      <div className={`sidebar d-none d-md-block`}>
        <div className="sidebar-content">
          {/* Logo Section */}
          <div className="sidebar-logo">
            <img
              src={logo}
              alt="blue caffeine"
              width={120}
              height={44}
              className="logo-img"
              onClick={() => navigate("/dashboard")}
              style={{ cursor: "pointer" }}
            />
          </div>
          {/* Menu Items */}
          <Nav className="sidebar-nav flex-column">
            {menuItems.map((item, index) => (
              <div key={item.key} className="sidebar-item-wrapper">
                {item.isButton ? (
                  <Button
                    variant="outline-primary"
                    className="sidebar-add-btn w-100 mb-3"
                    onClick={() => handleNavigation(item)}
                  >
                    <item.icon className="me-2" size={16} />
                    {item.name}
                  </Button>
                ) : (
                  <Nav.Link
                    href="#"
                    className={`sidebar-nav-item ${
                      activeItem === item.key ? "active" : ""
                    }`}
                    onClick={(e) => {
                      e.preventDefault();
                      handleNavigation(item);
                    }}
                  >
                    <item.icon className="sidebar-icon" size={18} />
                    <span className="sidebar-text">{item.name}</span>
                  </Nav.Link>
                )}
              </div>
            ))}
          </Nav>{" "}
          {/* User Profile Section */}
          <div className="sidebar-profile">
            <div className="profile-info">
              <div className="profile-avatar-icon">
                <FiUser size={20} />
              </div>
              <div className="profile-details">
                <div className="profile-name">{username}</div>
                {userId && <div className="profile-id">ID: {userId}</div>}
              </div>
            </div>
            <Dropdown align="end">
              <Dropdown.Toggle
                as={Button}
                variant="link"
                className="profile-menu-btn p-0"
                aria-label="Profile menu"
              >
                <FiMoreHorizontal size={16} />
              </Dropdown.Toggle>
              <Dropdown.Menu>
                <Dropdown.Item onClick={handleLogout} className="text-danger">
                  <FiLogOut className="me-2" size={16} />
                  {getTranslation(language, "sidebar.logout")}
                </Dropdown.Item>
              </Dropdown.Menu>
            </Dropdown>
          </div>
        </div>
      </div>
    </>
  );
}

export default Sidebar;
