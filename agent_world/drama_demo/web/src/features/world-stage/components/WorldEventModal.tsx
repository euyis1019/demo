import type { WorldEvent } from "../../../api/types";

export interface WorldEventModalProps {
  event: WorldEvent;
  onDismiss: () => void;
}

const KIND_LABELS: Record<WorldEvent["kind"], string> = {
  broadcast: "世界广播",
  phase_route: "新任务",
  place_mutation: "场景变化",
  bad_end: "Bad End",
  system: "系统事件",
};

export function WorldEventModal({ event, onDismiss }: WorldEventModalProps) {
  return (
    <div className="modal-backdrop modal-backdrop--world" role="presentation">
      <div
        className="world-event-modal"
        role="dialog"
        aria-modal="true"
        aria-label={event.title ?? KIND_LABELS[event.kind]}
      >
        <p className="world-event-modal__kind">{KIND_LABELS[event.kind]}</p>
        {event.title ? <h2 className="world-event-modal__title">{event.title}</h2> : null}
        <p className="world-event-modal__content">{event.content}</p>
        <footer className="world-event-modal__footer">
          <span className="world-event-modal__tick">t={event.at_tick}</span>
          <button type="button" className="world-event-modal__btn" onClick={onDismiss}>
            知道了
          </button>
        </footer>
      </div>
    </div>
  );
}
