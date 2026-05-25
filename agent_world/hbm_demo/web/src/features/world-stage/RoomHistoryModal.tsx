import type { GameMessage } from "../../api/types";
import { PLAYER_AGENT_ID } from "../../constants/agents";
import { placeDisplayName, type PlaceId } from "../../utils/places";
import { messageReactKey } from "../../utils/messages";
import { MessageBubble } from "../main-chat/MessageBubble";

export interface RoomHistoryModalProps {
  placeId: PlaceId;
  messages: GameMessage[];
  nameMap: Record<string, string>;
  onClose: () => void;
  onPromptClick?: (message: GameMessage) => void;
}

export function RoomHistoryModal({
  placeId,
  messages,
  nameMap,
  onClose,
  onPromptClick,
}: RoomHistoryModalProps) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="room-history-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${placeDisplayName(placeId)} 聊天记录`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="room-history-modal__header">
          <div>
            <h2>{placeDisplayName(placeId)}</h2>
            <p className="room-history-modal__subtitle">房间 F2F 聊天记录（按时间排序）</p>
          </div>
          <button type="button" className="modal-close" onClick={onClose}>
            关闭
          </button>
        </header>
        <div className="room-history-modal__body chat-message-list">
          {messages.length === 0 ? (
            <p className="agent-phone__empty">暂无对话记录</p>
          ) : (
            messages.map((message, index) => (
              <MessageBubble
                key={messageReactKey(message, index)}
                message={message}
                variant="f2f"
                inboxOwnerId={PLAYER_AGENT_ID}
                chatLayout
                nameMap={nameMap}
                onPromptClick={onPromptClick}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
