/**
 * F5 — 错误处理、loading elapsed、Runner 503 Modal（PLAN2 F5）。
 * F12 — 两栏 WorldStage + Agent 手机面板（dev_logs/32 §6）。
 * Story — 沉浸式剧情模式（dev_logs/feature/frontend-immersive-view）。
 */

import "./styles/global.css";
import { useEffect, useMemo } from "react";
import { MAX_TURNS } from "./constants/gameLoop";
import { agentDisplayName } from "./constants/agents";
import {
  BootScreen,
  EndingScreen,
  GameOverScreen,
  LoadingOverlay,
  PhaseToast,
  PlayerInput,
  RunnerNotReadyModal,
  StatusPanel,
  StoryModeStage,
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
import { agentsInPlace } from "./store/worldSync";
import { GameStoreProvider, useGameStoreContext } from "./store";
import { placeDisplayName, type PlaceId } from "./utils/places";
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

  // F18：剧情模式让世界持续运行（被暂停就自动恢复），保证 AIGC 画面不停更新。
  useEffect(() => {
    if (
      viewMode === "story" &&
      state.view === "playing" &&
      worldLoopState === "paused"
    ) {
      void resumeWorld();
    }
  }, [viewMode, state.view, worldLoopState, resumeWorld]);

  const {
    healthChecking,
    runnerReady,
    healthError,
    sessionInitialized,
    loading,
    phaseToast,
    stats,
    phase,
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
    lastError,
    runnerModalOpen,
    latestFrame,
  } = state;

  const presentAgents = useMemo(
    () =>
      agentsInPlace(agentLocations, placeId)
        .filter((id) => id !== "player")
        .map((id) => agentDisplayName(id, nameMap)),
    [agentLocations, placeId, nameMap],
  );

  const godModeInput = (
    <PlayerInput
      onSend={(text) => void sendTurn(text)}
      disabled={loading || view !== "playing"}
      placeholder="输入你的台词…"
    />
  );

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
              : "请先启动 run_hbm 与 Flask")
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
      <PhaseToast
        message={phaseToast}
        onDismiss={() => dispatch({ type: "DISMISS_PHASE_TOAST" })}
      />

      <RunnerNotReadyModal
        open={runnerModalOpen}
        onClose={() => dispatch({ type: "SET_RUNNER_MODAL", open: false })}
        onRetryHealth={() => void retryHealth()}
      />

      {isStoryMode ? (
        <StoryModeStage
          viewMode={viewMode}
          placeId={placeId as PlaceId}
          roomF2f={roomF2f}
          nameMap={nameMap}
          pendingWorldEvent={pendingWorldEvent}
          lastError={lastError}
          inputSlot={storyModeInput}
          frame={latestFrame}
          onToggleViewMode={toggleViewMode}
          onDismissWorldEvent={() => dispatch({ type: "DISMISS_WORLD_EVENT" })}
          {...worldControls}
        />
      ) : (
        <TwoColumnLayout
            status={
              <StatusPanel
                stats={stats}
                phase={phase}
                playerTurn={playerTurn}
                maxTurns={MAX_TURNS}
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
          description={
            badEndLine ??
            "你的技术阐述未能通过前台筛选，保安礼貌地请你离开 NVIDIA 总部。"
          }
        />
      ) : null}

      {view === "ending" && endingId ? (
        <EndingScreen endingId={endingId} onRestart={() => void restartGame()} />
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
