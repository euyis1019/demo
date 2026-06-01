/**
 * F5 — 错误处理、loading elapsed、Runner 503 Modal（PLAN2 F5）。
 * F12 — 两栏 WorldStage + Agent 手机面板（dev_logs/32 §6）。
 * Story — 沉浸式剧情模式（dev_logs/feature/frontend-immersive-view）。
 */

import "./styles/global.css";
import { useMemo } from "react";
import { agentDisplayName } from "./constants/agents";
import {
  BootScreen,
  EndingScreen,
  GameOverScreen,
  LoadingOverlay,
  OnboardingModal,
  PlayerInput,
  RunnerNotReadyModal,
  StatusPanel,
  StoryModeStage,
  StorySelectScreen,
  StoryPlayerInput,
  TwoColumnLayout,
  useGameLoop,
  useHealthCheck,
  useEnvStatus,
  useLoadingElapsed,
  useStartGame,
  useViewMode,
  useWorldDeltaSync,
  useWorldLoopControl,
  WorldStage,
} from "./features";
import { setSimId } from "./api/drama";
import { agentsInPlace } from "./store/worldSync";
import { GameStoreProvider, useGameStoreContext } from "./store";
import { deriveWorldPlaces, placeDisplayName, type PlaceId } from "./utils/places";
import { isPlayerSender } from "./utils/messages";

function GameApp() {
  const { state, dispatch } = useGameStoreContext();
  const { viewMode, toggleViewMode } = useViewMode();
  const { retryHealth } = useHealthCheck();
  const { startGame, restartGame, resetDemo } = useStartGame();
  const { sendTurn } = useGameLoop();
  const {
    worldLoopState,
    pauseDisabled,
    pauseWorld,
    resumeWorld,
  } = useWorldLoopControl(state.sessionInitialized && state.view === "playing");
  const envTick = useEnvStatus(
    state.sessionInitialized && state.view === "playing",
  );
  useWorldDeltaSync(
    state.sessionInitialized && state.view === "playing" && state.worldSyncReady,
    worldLoopState === "paused",
    envTick,
  );
  const loadingElapsed = useLoadingElapsed(state.loading);

  const {
    healthChecking,
    runnerReady,
    healthError,
    sessionInitialized,
    loading,
    stats,
    playerTurn,
    placeId,
    roomF2f,
    agentLocations,
    agentInbox,
    nameMap,
    worldTick,
    activeAgentModal,
    pendingWorldEvent,
    recentMoveKeys,
    recentRdcLinks,
    view,
    endingId,
    endingSummary,
    endingKind,
    onboarding,
    onboardingSeen,
    lastError,
    runnerModalOpen,
  } = state;

  const presentAgents = useMemo(
    () =>
      agentsInPlace(agentLocations, placeId)
        .filter((id) => id !== "player")
        .map((id) => agentDisplayName(id, nameMap)),
    [agentLocations, placeId, nameMap],
  );

  const worldPlaces = useMemo(
    () => deriveWorldPlaces(placeId, agentLocations, roomF2f),
    [placeId, agentLocations, roomF2f],
  );

  const godModeInput = (
    <PlayerInput
      onSend={(text) => void sendTurn(text)}
      disabled={loading || view !== "playing"}
      placeholder="输入你的台词…"
    />
  );

  // 剧情模式：只留台词输入框；移动→左侧地点列表、私信/群聊→收件箱下方发送栏、看信息→📱手机面板（见 StoryModeStage）。
  const storyModeInput = (
    <StoryPlayerInput
      onSend={(text) => void sendTurn(text)}
      disabled={loading || view !== "playing"}
      placeholder="输入你的台词…"
    />
  );

  const worldControls = {
    worldLoopState,
    pauseDisabled: pauseDisabled || view !== "playing",
    resetDisabled: loading,
    onPauseWorld: () => void pauseWorld(),
    onResumeWorld: () => void resumeWorld(),
    onReset: () => void resetDemo(),
  };

  if (view === "select") {
    return (
      <StorySelectScreen
        onReady={(simId) => {
          setSimId(simId);
          // 切到 boot 后，useHealthCheck 的 effect 会对这个新 sim 自动跑一次健康检查
          dispatch({ type: "ENTER_BOOT" });
        }}
      />
    );
  }

  if (healthChecking) {
    return (
      <>
        <BootScreen
          runnerReady={false}
          checking
          message="正在检测 Runner 与数据库状态…"
          onRetryHealth={() => void retryHealth()}
        />
        <RunnerNotReadyModal
          open={runnerModalOpen}
          onClose={() => dispatch({ type: "SET_RUNNER_MODAL", open: false })}
          onRetryHealth={() => void retryHealth()}
        />
      </>
    );
  }

  if (!sessionInitialized || view === "boot") {
    return (
      <>
        <BootScreen
          runnerReady={runnerReady}
          message={
            healthError ??
            (runnerReady
              ? "后端已就绪，点击开始游戏进入 Turn 1"
              : "请先启动 run_drama 与 Flask")
          }
          onStart={() => void startGame()}
          onRetryHealth={() => void retryHealth()}
        />
        <RunnerNotReadyModal
          open={runnerModalOpen}
          onClose={() => dispatch({ type: "SET_RUNNER_MODAL", open: false })}
          onRetryHealth={() => void retryHealth()}
        />
      </>
    );
  }

  const badEndLine =
    view === "game_over"
      ? Object.values(roomF2f)
          .flat()
          .filter((message) => !isPlayerSender(message.sender))
          .at(-1)?.content
      : undefined;

  const isStoryMode = viewMode === "story";

  return (
    <>
      {/* 进入新任务的提示只由「世界事件」横幅(WorldEventModal, kind=phase_route)统一呈现——
          剧情模式与上帝模式都已渲染它。原 PhaseToast 是第二个独立提示源，会让同一次推进「弹两遍」，故移除。 */}
      <RunnerNotReadyModal
        open={runnerModalOpen}
        onClose={() => dispatch({ type: "SET_RUNNER_MODAL", open: false })}
        onRetryHealth={() => void retryHealth()}
      />

      {onboarding && !onboardingSeen && view === "playing" ? (
        <OnboardingModal
          onboarding={onboarding}
          onDismiss={() => dispatch({ type: "DISMISS_ONBOARDING" })}
        />
      ) : null}

      {isStoryMode ? (
        <StoryModeStage
          viewMode={viewMode}
          placeId={placeId as PlaceId}
          roomF2f={roomF2f}
          nameMap={nameMap}
          agentMood={state.agentMood}
          playerInbox={state.agentInbox["0"]}
          agentLocations={agentLocations}
          places={worldPlaces}
          placesDisabled={loading || view !== "playing"}
          presentAgents={presentAgents}
          worldTick={envTick ?? worldTick}
          playerTurn={playerTurn}
          stats={state.stats}
          statsDimensions={state.statsDimensions}
          pendingWorldEvent={pendingWorldEvent}
          lastError={lastError}
          inputSlot={storyModeInput}
          onToggleViewMode={toggleViewMode}
          onDismissWorldEvent={() => dispatch({ type: "DISMISS_WORLD_EVENT" })}
          {...worldControls}
        />
      ) : (
        <TwoColumnLayout
            status={
              <StatusPanel
                stats={stats}
                dimensions={state.statsDimensions}
                playerTurn={playerTurn}
                placeLabel={placeDisplayName(placeId)}
                presentAgents={presentAgents}
                worldTick={envTick ?? worldTick}
                worldLoopState={worldLoopState}
                onPauseWorld={() => void pauseWorld()}
                onResumeWorld={() => void resumeWorld()}
                pauseDisabled={pauseDisabled || view !== "playing"}
                onReset={() => void resetDemo()}
                resetDisabled={loading}
                onSwitchToStoryMode={toggleViewMode}
              />
            }
            main={
              <WorldStage
                roomF2f={roomF2f}
                playerPlaceId={placeId as PlaceId}
                agentLocations={agentLocations}
                agentInbox={agentInbox}
                nameMap={nameMap}
                recentMoveKeys={recentMoveKeys}
                recentRdcLinks={recentRdcLinks}
                activeAgentModal={activeAgentModal}
                pendingWorldEvent={pendingWorldEvent}
                lastError={lastError}
                onAgentClick={(agentId) =>
                  dispatch({ type: "OPEN_AGENT_MODAL", agentId })
                }
                onCloseAgentModal={() => dispatch({ type: "CLOSE_AGENT_MODAL" })}
                onDismissWorldEvent={() =>
                  dispatch({ type: "DISMISS_WORLD_EVENT" })
                }
                onClearRecentMoves={() => dispatch({ type: "CLEAR_RECENT_MOVES" })}
                onClearRecentRdcLinks={() =>
                  dispatch({ type: "CLEAR_RECENT_RDC_LINKS" })
                }
                inputSlot={godModeInput}
              />
            }
          />
      )}

      <LoadingOverlay
        visible={loading}
        message="Agent 世界运转中，等待 NPC 响应…"
        elapsedSeconds={loadingElapsed}
      />

      {view === "game_over" ? (
        <GameOverScreen
          onRestart={() => void restartGame()}
          description={endingSummary || badEndLine || undefined}
        />
      ) : null}

      {view === "ending" && endingId ? (
        <EndingScreen
          endingId={endingId}
          summary={endingSummary}
          kind={endingKind}
          onRestart={() => void restartGame()}
        />
      ) : null}
    </>
  );
}

export default function App() {
  return (
    <GameStoreProvider>
      <GameApp />
    </GameStoreProvider>
  );
}
