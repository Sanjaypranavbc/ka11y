import { useState, useEffect, useRef } from "react";
import VoiceOrb from "./VoiceOrb";
import { useNavigate } from "react-router-dom";
import CallButton from "./CallButton";
import StatusBadge from "./StatusBadge";
import { getAllCharacters, defaultCharacters } from "../../utils/characters";
import { MessageSquare } from "lucide-react";
import { Room, RoomEvent, Track } from "livekit-client";
import "./VoiceAgent.css";
import LanguageSelector, {
  useLanguage,
} from "../../Components/LanguageSelector";
import { getTranslation } from "../../utils/translations";
import axiosInstance from "../../utils/axios";

const VoiceAgent = () => {
  const { language } = useLanguage();
  const navigate = useNavigate();
  const hasCheckedSession = useRef(false);

  const [isCallActive, setIsCallActive] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [selectedCharacter, setSelectedCharacter] = useState(
    defaultCharacters[0]
  );
  const [status, setStatus] = useState("idle");
  const [greeting, setGreeting] = useState("");
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([]);

  const roomRef = useRef(null);
  const audioContainerRef = useRef(null);
  const messagesEndRef = useRef(null);

  /* Scroll chat */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /* Load selected character */
  useEffect(() => {
    const storedId = localStorage.getItem("selectedCharacter");
    if (storedId) {
      const found = getAllCharacters().find((c) => c.id === storedId);
      if (found) setSelectedCharacter(found);
    }
  }, []);

  /* Cleanup */
  useEffect(() => {
    return () => roomRef.current?.disconnect();
  }, []);

  const [userId, setUserId] = useState("187");
  const [collectionName, setCollectionName] = useState("pole_saw_1");

  useEffect(() => {
    if (hasCheckedSession.current) return;

    const storedUserId = sessionStorage.getItem("chatUserId");
    const storedCollectionName = sessionStorage.getItem("chatCollectionName");

    if (!storedUserId || !storedCollectionName) {
      navigate("/dashboard", { replace: true });
      return;
    }

    setUserId(storedUserId);
    setCollectionName(storedCollectionName);

    hasCheckedSession.current = true;
  }, [navigate]);

  const connectToVoiceAgent = async () => {
    setStatus("connecting");
    setError(null);

    try {
      const { data: tokenResponse } = await axiosInstance.post(
        "/voice/token",
        {
          user_id: userId,
          user_name: "User",
          collection_name: collectionName,
        }
      );

      const { token, url, room_name } = tokenResponse;

      await axiosInstance.post(
        "/voice/session/start",
        {
          user_id: userId,
          room_name,
          collection_name: collectionName,
          user_name: "User",
        }
      );

      const room = new Room();
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) {
          const audio = track.attach();
          audio.autoplay = true;
          audioContainerRef.current?.appendChild(audio);
        }
      });

      room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        const text = segments.map((s) => s.text).join(" ");
        if (!text) return;

        const isAgent = participant !== room.localParticipant;
        setMessages((prev) => [...prev, { text, isAgent }]);
      });

      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        const agentSpeaking = speakers.some((s) => s !== room.localParticipant);
        setIsSpeaking(agentSpeaking);
        setStatus(agentSpeaking ? "speaking" : "active");
      });

      room.on(RoomEvent.Disconnected, () => {
        setIsCallActive(false);
        setStatus("idle");
        setGreeting("");
        setIsSpeaking(false);
        setMessages([]);
      });

      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true);

      setIsCallActive(true);
      setStatus("active");
      setGreeting(`Connected to ${selectedCharacter.name}`);
    } catch (err) {
      setError(err.message);
      setStatus("idle");
    }
  };

  const handleCallToggle = () => {
    if (status === "connecting") return;
    isCallActive ? roomRef.current?.disconnect() : connectToVoiceAgent();
  };

  return (
    <div>
      <div className="language-selector-fixed">
        <LanguageSelector />
      </div>
      <div className="chat-messages-area">
        <div className="chat-messages-container">
          <div className="overflow-hidden">
            <div ref={audioContainerRef} className="d-none" />

            <main className="position-relative z-1 d-flex flex-column align-items-center justify-content-center px-3 pt-md-5 pb-4">
              {/* Character */}
              <div className="mb-3">
                <button className="btn glass-card d-flex align-items-center gap-2 rounded-pill">
                  <span className="fs-4"> <img src={selectedCharacter.icon} alt={selectedCharacter.name} /></span>
                  <div className="text-start">
                    <div className="fw-medium">{selectedCharacter.name}</div>
                    <small className="text-muted">
                      {selectedCharacter.tone}
                    </small>
                  </div>
                </button>
              </div>

              {/* Status */}
              <div className="mb-0 mb-md-4">
                <StatusBadge status={status} />
              </div>

              {/* Voice Orb */}
              <div className="mb-0 mb-md-4">
                <VoiceOrb
                  isActive={isCallActive}
                  isSpeaking={isSpeaking}
                  className="orb-lg"
                />
              </div>

              {/* Greeting */}
              {greeting && (
                <div
                  className="text-center mb-4 w-100"
                  style={{ maxWidth: 420 }}
                >
                  <div className="glass-card p-3 rounded-3">
                    <div className="d-flex gap-3">
                      <div className="icon-box">
                        <MessageSquare size={18} />
                      </div>
                      <p className="mb-0 text-start">{greeting}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Error */}
              {error && <div className="text-danger mb-3">{error}</div>}

              {/* Transcript */}
              {isCallActive && messages.length > 0 && (
                <div className="position-absolute top-0 end-0 m-3 glass-card p-3 rounded-3 transcript-box">
                  {messages.map((msg, i) => (
                    <div
                      key={i}
                      className={`mb-2 text-${
                        msg.isAgent ? "start text-primary" : "end"
                      }`}
                    >
                      <small className="fw-bold d-block">
                        {msg.isAgent ? "Agent" : "You"}
                      </small>
                      <span className="badge bg-secondary bg-opacity-25 text-wrap">
                        {msg.text}
                      </span>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              )}

              {/* Call Button */}
              <CallButton isActive={isCallActive} onToggle={handleCallToggle} />

              <p className="small">
                {getTranslation(language, isCallActive ? "voice.tapToEndCall" : "voice.tapToStartVoiceCall")}
              </p>
            </main>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VoiceAgent;
