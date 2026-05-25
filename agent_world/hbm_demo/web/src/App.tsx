/**
 * F5 — 错误处理、loading elapsed、Runner 503 Modal（PLAN2 F5）。
 * F12 — 两栏 WorldStage + Agent 手机面板（dev_logs/32 §6）。
 */

import "./styles/global.css";
import { useMemo } from "react";
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
  TwoColumnLayout,
  useGameLoop,
  useHealthCheck,
  useLoadingElapsed,
  useStartGame,
  useWorldDeltaPoll,
  useWorldLoopControl,
  WorldStage,
} from "./features";
import { useEnvStatus } from "./features/observer/useEnvStatus";
import { agentsInPlace } from "./store/worldSync";
import { GameStoreProvider, useGameStoreContext } from "./store";
import { placeDisplayName } from "./utils/places";
import { isPlayerSender } from "./utils/messages";

function GameApp() {
  const { state, dispatch } = useGameStoreContext();
  const { retryHealth } = useHealthCheck();
  const { startGame, restartGame, resetDemo } = useStartGame();
  const { sendTurn } = useGameLoop();
  const {
    worldLoopState,
    pauseDisabled,
    pauseWorld,
    resumeWorld,
  } = useWorldLoopControl(state.sessionInitialized && state.view === "playing");
  useWorldDeltaPoll(
    state.sessionInitialized && state.view === "playing",
    worldLoopState === "paused",
  );
  const loadingElapsed = useLoadingElapsed(state.loading);
  const envTick = useEnvStatus(
    state.sessionInitialized && state.view === "playing" && state.worldLoopState !== "paused",
  );

  const {
    healthChecking,
    runnerReady,
    healthError,
    sessionInitialized,
    loading,
    immediateMsg,
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
  } = state;

  const presentAgents = useMemo(
    () =>
      agentsInPlace(agentLocations, placeId)
        .filter((id) => id !== "player")
        .map((id) => agentDisplayName(id, nameMap)),
    [agentLocations, placeId, nameMap],
  );

  if (healthChecking) {
    return (
      <>
        <BootScreen
          runnerReady={false}
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
          />
        }
        main={
          <WorldStage
            roomF2f={roomF2f}
            agentLocations={agentLocations}
            agentInbox={agentInbox}
            nameMap={nameMap}
            recentMoveKeys={recentMoveKeys}
            recentRdcLinks={recentRdcLinks}
            activeAgentModal={activeAgentModal}
            pendingWorldEvent={pendingWorldEvent}
            immediateMsg={immediateMsg}
            lastError={lastError}
            onAgentClick={(agentId) =>
              dispatch({ type: "OPEN_AGENT_MODAL", agentId })
            }
            onCloseAgentModal={() => dispatch({ type: "CLOSE_AGENT_MODAL" })}
            onDismissWorldEvent={() => dispatch({ type: "DISMISS_WORLD_EVENT" })}
            onClearRecentMoves={() => dispatch({ type: "CLEAR_RECENT_MOVES" })}
            onClearRecentRdcLinks={() => dispatch({ type: "CLEAR_RECENT_RDC_LINKS" })}
            inputSlot={
              <PlayerInput
                onSend={(text) => void sendTurn(text)}
                disabled={loading || view !== "playing"}
                placeholder="输入你的台词…"
              />
            }
          />
        }
      />

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
