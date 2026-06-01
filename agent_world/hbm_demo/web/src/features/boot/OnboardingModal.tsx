import type { Onboarding } from "../../api/types";

export interface OnboardingModalProps {
  onboarding: Onboarding;
  onDismiss: () => void;
}

/** 开局新手引导弹窗：展示管理 agent 生成的故事背景 + 此刻可做的行为，确认后进入游玩。只显示一次。 */
export function OnboardingModal({ onboarding, onDismiss }: OnboardingModalProps) {
  const tips = (onboarding.tips ?? []).filter(Boolean);
  return (
    <div className="screen-overlay onboarding-modal" role="dialog" aria-modal="true">
      <div className="onboarding-modal__card">
        <p className="onboarding-modal__badge">开始之前</p>
        {onboarding.title ? (
          <h1 className="onboarding-modal__title">{onboarding.title}</h1>
        ) : null}
        {onboarding.background ? (
          <p className="onboarding-modal__bg">{onboarding.background}</p>
        ) : null}
        {tips.length ? (
          <>
            <h2 className="onboarding-modal__sub">你现在可以做什么</h2>
            <ul className="onboarding-modal__tips">
              {tips.map((tip, i) => (
                <li key={i}>{tip}</li>
              ))}
            </ul>
          </>
        ) : null}
        <button type="button" className="btn btn--primary" onClick={onDismiss}>
          开始游玩
        </button>
      </div>
    </div>
  );
}
