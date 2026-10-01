import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import Sidebar from "../Components/Header";
import ChatHeader from "./ChatHeader";
import ChatWindow from "./ChatWindow";
import "./chat.css";

const Chat = () => {
  const navigate = useNavigate();
  const hasCheckedSession = useRef(false);

  useEffect(() => {
    // Only check once on mount
    if (!hasCheckedSession.current) {
      const collectionName = sessionStorage.getItem("chatCollectionName");

      if (!collectionName) {
        // Redirect to dashboard if no collection name
        navigate("/dashboard", { replace: true });

        return;
      }

      hasCheckedSession.current = true;
    }
  }, [navigate]);

  return (
    <div className="chat-layout">
      <Sidebar />
      <div className="main-content">
        <div className="chat-container">
          <ChatHeader />
          <ChatWindow />
        </div>
      </div>
    </div>
  );
};

export default Chat;
