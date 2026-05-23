/**
 * F2 — 三屏 Mock 布局（PLAN2 F2 / dev_logs/03）。
 * BootScreen / LoadingOverlay / 结局屏组件已就绪，F3+ 接入 store 与 API。
 */

import "./styles/global.css";
import {
  MainChat,
  ObserverPanel,
  PlayerInput,
  StatusPanel,
  ThreeColumnLayout,
} from "./components";
import {
  MOCK_F2F_MESSAGES,
  MOCK_GRP_MESSAGES,
  MOCK_IMMEDIATE_MSG,
  MOCK_MAX_TURNS,
  MOCK_PHASE,
  MOCK_PLACE_LABEL,
  MOCK_PLAYER_TURN,
  MOCK_PRESENT_AGENTS,
  MOCK_RDC_MESSAGES,
  MOCK_STATS,
} from "./mock/demoSnapshot";

function App() {
  return (
    <ThreeColumnLayout
      status={
        <StatusPanel
          stats={MOCK_STATS}
          phase={MOCK_PHASE}
          playerTurn={MOCK_PLAYER_TURN}
          maxTurns={MOCK_MAX_TURNS}
          placeLabel={MOCK_PLACE_LABEL}
          presentAgents={MOCK_PRESENT_AGENTS}
        />
      }
      main={
        <MainChat messages={MOCK_F2F_MESSAGES} immediateMsg={MOCK_IMMEDIATE_MSG}>
          <PlayerInput placeholder="输入你的台词…（F3 接 API）" />
        </MainChat>
      }
      observer={
        <ObserverPanel
          rdcMessages={MOCK_RDC_MESSAGES}
          grpMessages={MOCK_GRP_MESSAGES}
        />
      }
    />
  );
}

export default App;
