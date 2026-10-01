import React, { createContext, useContext, useState } from "react";
import { Dropdown } from "react-bootstrap";
import { FiChevronDown } from "react-icons/fi";
import "./LanguageSelector.css";

// Language Context
const LanguageContext = createContext();

// Language Provider Component
export const LanguageProvider = ({ children }) => {
  const [language, setLanguage] = useState("EN");

  const changeLanguage = (lang) => {
    setLanguage(lang);
    // Store in localStorage for persistence
    localStorage.setItem("selectedLanguage", lang);
  };

  // Initialize from localStorage on mount
  React.useEffect(() => {
    const savedLanguage = localStorage.getItem("selectedLanguage");
    if (savedLanguage) {
      setLanguage(savedLanguage);
    }
  }, []);

  return (
    <LanguageContext.Provider value={{ language, changeLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
};

// Hook to use language context
export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within a LanguageProvider");
  }
  return context;
};

// Language Selector Component
const LanguageSelector = () => {
  const { language, changeLanguage } = useLanguage();

  const handleLanguageSelect = (selectedLanguage) => {
    changeLanguage(selectedLanguage);
  };

  const languageOptions = [
    { 
      code: "EN", 
      label: "EN", 
      flag: (
        <svg width="16" height="12" viewBox="0 0 16 12" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="16" height="12" fill="#B22234"/>
          <rect width="16" height="0.923" y="0.923" fill="white"/>
          <rect width="16" height="0.923" y="2.769" fill="white"/>
          <rect width="16" height="0.923" y="4.615" fill="white"/>
          <rect width="16" height="0.923" y="6.462" fill="white"/>
          <rect width="16" height="0.923" y="8.308" fill="white"/>
          <rect width="16" height="0.923" y="10.154" fill="white"/>
          <rect width="6.4" height="6.462" fill="#3C3B6E"/>
        </svg>
      )
    },
    { 
      code: "JA", 
      label: "JA", 
      flag: (
        <svg width="16" height="12" viewBox="0 0 16 12" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="16" height="12" fill="white"/>
          <circle cx="8" cy="6" r="3.2" fill="#BC002D"/>
        </svg>
      )
    },
  ];

  const currentLanguage = languageOptions.find(
    (lang) => lang.code === language
  );

  return (
    <div className="language-selector-dropdown">
      <Dropdown>
        <Dropdown.Toggle
          variant="outline-secondary"
          id="language-dropdown"
          className="language-dropdown-toggle"
        >
          <span className="flag-icon">{currentLanguage?.flag}</span>
          <span className="language-text">{currentLanguage?.label}</span>
          <FiChevronDown className="dropdown-arrow" />
        </Dropdown.Toggle>

        <Dropdown.Menu className="language-dropdown-menu">
          {languageOptions.map((option) => (
            <Dropdown.Item
              key={option.code}
              onClick={() => handleLanguageSelect(option.code)}
              className={`language-dropdown-item ${
                language === option.code ? "active" : ""
              }`}
            >
              <span className="flag-icon">{option.flag}</span>
              <span className="language-text">{option.label}</span>
            </Dropdown.Item>
          ))}
        </Dropdown.Menu>
      </Dropdown>
    </div>
  );
};

export default LanguageSelector;
