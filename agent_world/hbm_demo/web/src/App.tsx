/**
 * F5 — 错误处理、loading elapsed、Runner 503 Modal（PLAN2 F5）。
 */

import "./styles/global.css";
import { MAX_TURNS } from "./constants/gameLoop";
import {
  BootScreen,
  EndingScreen,
  GameOverScreen,
  LoadingOverlay,
  MainChat,
  ObserverPanel,
  PhaseToast,
  PlayerInput,
  RunnerNotReadyModal,
  StatusPanel,
  ThreeColumnLayout,
  useEnvStatus,
  useGameLoop,
  useHealthCheck,
  useLoadingElapsed,
  useStartGame,
} from "./features";
import { GameStoreProvider, useGameStoreContext } from "./store";
import { placeDisplayName } from "./utils/places";

function GameApp() {
  const { state, dispatch } = useGameStoreContext();
  const { retryHealth } = useHealthCheck();
  const { startGame, restartGame, resetDemo } = useStartGame();
  const { sendTurn } = useGameLoop();
  const loadingElapsed = useLoadingElapsed(state.loading);
  const envTick = useEnvStatus(state.sessionInitialized && state.view === "playing");

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
    f2fMessages,
    rdcMessages,
    grpMessages,
    view,
    endingId,
    lastError,
    runnerModalOpen,
  } = state;

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
      ? f2fMessages.filter((m) => m.sender !== "玩家").at(-1)?.content
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

      <ThreeColumnLayout
        status={
          <StatusPanel
            stats={stats}
            phase={phase}
            playerTurn={playerTurn}
            maxTurns={MAX_TURNS}
            placeLabel={placeDisplayName(placeId)}
            onReset={() => void resetDemo()}
            resetDisabled={loading}
          />
        }
        main={
          <MainChat messages={f2fMessages} immediateMsg={immediateMsg}>
            {lastError ? (
              <p className="game-error" role="alert">
                {lastError}
              </p>
            ) : null}
            <PlayerInput
              onSend={(text) => void sendTurn(text)}
              disabled={loading || view !== "playing"}
              placeholder="输入你的台词…"
            />
          </MainChat>
        }
        observer={
          <ObserverPanel
            rdcMessages={rdcMessages}
            grpMessages={grpMessages}
            currentTick={envTick}
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
