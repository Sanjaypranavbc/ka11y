import "./App.css";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Login from "./Login/Login";
import Dashboard from "./dashboard";
import Chat from "./chat";
import Voice from "./voice";
import ProductList from "./products/ProductList";
import PersonaSettings from "./personaSettings/PersonaSettings";
import DocUpload from "./docUpload/DocUpload";
import VoiceSettings from "./voiceSettings/VoiceSettings";
import { LanguageProvider } from "./Components/LanguageSelector";
import ProtectedRoute from "./Components/ProtectedRoute";
import ErrorBoundary from "./Components/ErrorBoundary";

function App() {
  return (
    <ErrorBoundary>
      <LanguageProvider>
        <div className="App">
          <Router>
            <Routes>
              <Route path="/" element={<Login />} />
              <Route path="/login" element={<Login />} />
              <Route
                path="/dashboard"
                element={
                  <ProtectedRoute>
                    <Dashboard />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/chat"
                element={
                  <ProtectedRoute>
                    <Chat />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/voice"
                element={
                  <ProtectedRoute>
                    <Voice />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/products"
                element={
                  <ProtectedRoute>
                    <ProductList />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/doc-upload"
                element={
                  <ProtectedRoute>
                    <DocUpload />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/persona-settings"
                element={
                  <ProtectedRoute>
                    <PersonaSettings />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/voice-settings"
                element={
                  <ProtectedRoute>
                    <VoiceSettings />
                  </ProtectedRoute>
                }
              />
              <Route path="*" element={<Login />} />
            </Routes>
          </Router>
        </div>
      </LanguageProvider>
    </ErrorBoundary>
  );
}

export default App;
