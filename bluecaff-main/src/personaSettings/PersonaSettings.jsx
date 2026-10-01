import React, { useState } from "react";
import { Container, Card, Button, Form, Row, Col } from "react-bootstrap";
import LanguageSelector, { useLanguage } from "../Components/LanguageSelector";
import Sidebar from "../Components/Header";
import { getTranslation } from "../utils/translations";
import "./PersonaSettings.css";
import personalHeaderIcon from "../assets/icons/personal_sett-header-icon.png";
import responseStyleIcon from "../assets/icons/response-style-icon.png";
import changeStyleIcon from "../assets/icons/change-sett-icon.png";
import perfStyleIcon from "../assets/icons/change-perf-icon.png";

function PersonaSettings() {
  const { language } = useLanguage();

  // State for response style selection
  const [responseStyle, setResponseStyle] = useState("customPersonality");

  // State for personality traits (0-10 scale)
  const [personalityTraits, setPersonalityTraits] = useState({
    warmth: 10,
    curiosity: 6,
    conciseness: 7,
    confidence: 7,
    energy: 8,
    empathy: 10,
    formality: 4,
    patience: 8,
    humor: 6,
    creativity: 6,
  });

  /* Commented out - not currently used */
  const handleTraitChange = (trait, value) => {
    setPersonalityTraits((prev) => ({
      ...prev,
      [trait]: parseInt(value),
    }));
  };
  

  const handleReset = () => {
    setPersonalityTraits({
      warmth: 5,
      curiosity: 5,
      conciseness: 5,
      confidence: 5,
      energy: 5,
      empathy: 5,
      formality: 5,
      patience: 5,
      humor: 5,
      creativity: 5,
    });
  };

  const handleSave = () => {
    console.log("Saving personality settings:", {
      // responseStyle,
      personalityTraits,
    });
    // Add save logic here
  };

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
                    alt="Persona Settings"
                    width={54}
                    height={54}
                  />
                </div>
                <div className="header-text">
                  <h1 className="page-title">
                    {getTranslation(language, "personaSettings.pageTitle")}
                  </h1>
                  <p className="page-subtitle">
                    {getTranslation(language, "personaSettings.pageSubtitle")}
                  </p>
                </div>
              </div>
            </div>

            {/* Settings Card */}
            <Card className="settings-card">
              <Card.Body className="settings-card-body">
                {/* Response Style Section - Commented Out */}
                
                <div className="settings-section">
                  <div className="section-header">
                    <div className="section-icon">
                      <img
                        src={responseStyleIcon}
                        alt="Response Style"
                        width={24}
                        height={24}
                      />
                    </div>
                    <h3 className="section-title">
                      {getTranslation(
                        language,
                        "personaSettings.responseStyle"
                      )}
                    </h3>
                  </div>

                  <div className="response-style-options">
                    <Form.Check
                      type="radio"
                      name="responseStyle"
                      id="friendly"
                      label={getTranslation(
                        language,
                        "personaSettings.friendly"
                      )}
                      checked={responseStyle === "friendly"}
                      onChange={() => setResponseStyle("friendly")}
                      className="style-checkbox"
                    />
                    <Form.Check
                      type="radio"
                      name="responseStyle"
                      id="professional"
                      label={getTranslation(
                        language,
                        "personaSettings.professional"
                      )}
                      checked={responseStyle === "professional"}
                      onChange={() => setResponseStyle("professional")}
                      className="style-checkbox"
                    />
                    <Form.Check
                      type="radio"
                      name="responseStyle"
                      id="casual"
                      label={getTranslation(language, "personaSettings.casual")}
                      checked={responseStyle === "casual"}
                      onChange={() => setResponseStyle("casual")}
                      className="style-checkbox"
                    />
                    <Form.Check
                      type="radio"
                      name="responseStyle"
                      id="technical"
                      label={getTranslation(
                        language,
                        "personaSettings.technical"
                      )}
                      checked={responseStyle === "technical"}
                      onChange={() => setResponseStyle("technical")}
                      className="style-checkbox"
                    />
                    <Form.Check
                      type="radio"
                      name="responseStyle"
                      id="customPersonality"
                      label={getTranslation(
                        language,
                        "personaSettings.customPersonality"
                      )}
                      checked={responseStyle === "customPersonality"}
                      onChange={() => setResponseStyle("customPersonality")}
                      className="style-checkbox"
                    />
                  </div>
                </div>
                

                {/* Custom Personality Style Section */}
                <div className="settings-section">
                  <div className="section-header">
                    <div className="section-icon">
                      <img
                        src={changeStyleIcon}
                        alt="Custom Personality Style"
                        width={24}
                        height={24}
                      />
                    </div>
                    <h3 className="section-title">
                      {getTranslation(
                        language,
                        "personaSettings.customPersonalityStyle"
                      )}
                    </h3>
                  </div>

                  {/* Note Section */}
                  {/* <div className="note-container">
                    <p className="note-text">
                      {getTranslation(language, "personaSettings.noteText") ||
                        "The Personality Settings feature lets you choose how the assistant behaves and communicates. Currently, it has built-in styles like Friendly, Professional, Casual, and Technical. In the near future, you can create your own custom personalities with unique characteristics, languages and tones. You can also add brand guidelines, and related company and compliance guidelines so that every response reflects your brand's voice, style, and communication standards, while meeting compliance requirements. Customize how your Chatbot / Virtual Assistant speaks and expresses itself so every interaction feels consistent and personalized."}
                    </p>
                  </div> */}

                  {/* Commented out personality traits sliders */}
                  <div className="personality-traits">
                    <Row>
                      <Col md={6}>
                        {Object.entries(personalityTraits)
                          .slice(0, 5)
                          .map(([trait, value]) => (
                            <div key={trait} className="trait-slider">
                              <div className="trait-header">
                                <label className="trait-label">
                                  {getTranslation(
                                    language,
                                    `personaSettings.traits.${trait}`
                                  )}
                                </label>
                                <span className="trait-value">{value}</span>
                              </div>
                              <Form.Range
                                min="0"
                                max="10"
                                value={value}
                                onChange={(e) =>
                                  handleTraitChange(trait, e.target.value)
                                }
                                className="trait-range"
                                style={{
                                  "--progress": `${(value / 10) * 100}%`,
                                }}
                              />
                            </div>
                          ))}
                      </Col>
                      <Col md={6}>
                        {Object.entries(personalityTraits)
                          .slice(5, 10)
                          .map(([trait, value]) => (
                            <div key={trait} className="trait-slider">
                              <div className="trait-header">
                                <label className="trait-label">
                                  {getTranslation(
                                    language,
                                    `personaSettings.traits.${trait}`
                                  )}
                                </label>
                                <span className="trait-value">{value}</span>
                              </div>
                              <Form.Range
                                min="0"
                                max="10"
                                value={value}
                                onChange={(e) =>
                                  handleTraitChange(trait, e.target.value)
                                }
                                className="trait-range"
                                style={{
                                  "--progress": `${(value / 10) * 100}%`,
                                }}
                              />
                            </div>
                          ))}
                      </Col>
                    </Row>
                  </div>
                  
                </div>
                {/* Custom Preference */}
                <div className="settings-section">
                  <div className="section-header">
                    <div className="section-icon">
                      <img
                        src={perfStyleIcon}
                        alt="Custom Preference"
                        width={24}
                        height={24}
                      />
                    </div>
                    <h3 className="section-title">
                      {getTranslation(
                        language,
                        "personaSettings.customPreference"
                      )}
                    </h3>
                  </div>
                  {/* Commented out personality traits sliders */}
                  <div className="personality-traits mt-0">
                    <Row>
                      <Col sm={12} md={6} className="mb-0">
                        <Form.Group>
                          <Form.Control 
                          id="custompreference"
                          as="textarea" 
                          rows={3}   
                          onChange={() => setResponseStyle("custompreference")}
                          style={{ resize: 'none' }}  
                          />
                        </Form.Group>
                      </Col>
                    </Row>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="action-buttons">
                  <Button
                    variant="outline-dark"
                    className="reset-button"
                    onClick={handleReset}
                  >
                    {getTranslation(language, "personaSettings.resetButton")}
                  </Button>
                  <Button
                    variant="dark"
                    className="save-button"
                    onClick={handleSave}
                  >
                    {getTranslation(language, "personaSettings.saveButton")}
                  </Button>
                </div>
              </Card.Body>
            </Card>
          </Container>
        </div>
      </div>
    </div>
  );
}

export default PersonaSettings;
