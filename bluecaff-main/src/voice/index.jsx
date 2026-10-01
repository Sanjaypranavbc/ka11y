import Sidebar from "../Components/Header";
import ChatHeader from "./ChatHeader";
import VoiceAgent from "./components/VoiceAgent";
import "./voice.css";

const Voice = () => {
  return (
    <div className="chat-layout">
      <Sidebar />
      <div className="main-content">
        <div className="chat-container">
          <ChatHeader />
          <VoiceAgent />
        </div>
      </div>
    </div>
  );
};

export default Voice;
