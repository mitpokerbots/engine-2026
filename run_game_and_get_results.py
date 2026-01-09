import engine
import gamelog_analyzer

if __name__ == "__main__":
    engine.Game().run()
    P1_bankroll, P1_PnL, P2_bankroll, P2_PnL = gamelog_analyzer.AnalyzeGame()
