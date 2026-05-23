/**
 * F3 — 游戏主循环：health → session/start → sendTurn + poll（PLAN2 F3）。
 */

import "./styles/global.css";
import {
  BootScreen,
  EndingScreen,
  GameOverScreen,
  LoadingOverlay,
  MainChat,
  ObserverPanel,
  PlayerInput,
  StatusPanel,
  ThreeColumnLayout,
} from "./components";
import { MAX_TURNS } from "./constants/gameLoop";
import { useGameLoop, useHealthCheck, useStartGame } from "./hooks";
import { GameStoreProvider, useGameStoreContext } from "./store";
import { placeDisplayName } from "./utils/places";

function GameApp() {
  const { state } = useGameStoreContext();
  const { retryHealth } = useHealthCheck();
  const { startGame } = useStartGame();
  const { sendTurn } = useGameLoop();

  const {
    healthChecking,
    runnerReady,
    healthError,
    sessionInitialized,
    loading,
    immediateMsg,
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
  } = state;

  if (healthChecking) {
    return (
      <BootScreen
        runnerReady={false}
        message="正在检测 Runner 与数据库状态…"
        onRetryHealth={() => void retryHealth()}
      />
    );
  }

  if (!sessionInitialized || view === "boot") {
    return (
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
    );
  }

  return (
    <>
      <ThreeColumnLayout
        status={
          <StatusPanel
            stats={stats}
            phase={phase}
            playerTurn={playerTurn}
            maxTurns={MAX_TURNS}
            placeLabel={placeDisplayName(placeId)}
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
          />
        }
      />

      <LoadingOverlay
        visible={loading}
        message="Agent 世界运转中，等待 NPC 响应…"
      />

      {view === "game_over" ? (
        <GameOverScreen onRestart={() => void startGame()} />
      ) : null}

      {view === "ending" && endingId ? (
        <EndingScreen endingId={endingId} onRestart={() => void startGame()} />
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
