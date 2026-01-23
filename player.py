'''
Poker Bot v4.0
Core Strategies:
1. Winning Probability (Outs × 4% / 2%)
2. Positional Advantage + Top20% Aggression
3. Opponent Modeling + Exploitation
4. Bankroll Protection
'''

from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, DiscardAction
from skeleton.states import GameState, TerminalState, RoundState
from skeleton.states import NUM_ROUNDS, STARTING_STACK, BIG_BLIND, SMALL_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot
import random
from collections import deque


class PokerMath:
    @staticmethod
    def count_outs(my_cards, board_cards, RANK_MAP):
        """Calculate Outs"""
        all_cards = list(my_cards) + list(board_cards)
        all_ranks = [RANK_MAP[c[0]] for c in all_cards]
        all_suits = [c[1] for c in all_cards]
        my_ranks = [RANK_MAP[c[0]] for c in my_cards]
        my_suits = [c[1] for c in my_cards]
        outs = 0
        draw_type = None
        
        # Flush Draw
        suit_counts = {'s': 0, 'h': 0, 'd': 0, 'c': 0}
        for s in all_suits:
            suit_counts[s] += 1
        max_suit_count = max(suit_counts.values())
        
        if max_suit_count == 4:
            outs += 9
            draw_type = 'flush'
        
        # Straight Draw
        unique_ranks = sorted(set(all_ranks))
        if 14 in unique_ranks:  
            unique_ranks_with_ace = [1] + unique_ranks
        else:
            unique_ranks_with_ace = unique_ranks
        
        max_straight_draw = 0
        for base in unique_ranks_with_ace:
            window = [x for x in unique_ranks_with_ace if base <= x < base + 5]
            if len(window) >= 4:
                max_straight_draw = max(max_straight_draw, len(window))
        
        if max_straight_draw == 4:
            if outs == 0:
                outs += 8
                draw_type = 'straight'
            else:
                outs += 6  
                draw_type = 'combo'
        
        # Pair to Trips
        rank_counts = {}
        for r in my_ranks:
            rank_counts[r] = rank_counts.get(r, 0) + 1
        
        if any(count == 2 for count in rank_counts.values()):
            pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
            if outs == 0:
                outs += 2
                draw_type = 'pair_to_trips'
        
        #Two Pair to Full House
        board_rank_counts = {}
        for r in [RANK_MAP[c[0]] for c in board_cards]:
            board_rank_counts[r] = board_rank_counts.get(r, 0) + 1
        all_rank_counts = {}
        for r in all_ranks:
            all_rank_counts[r] = all_rank_counts.get(r, 0) + 1

        num_pairs = sum(1 for c in all_rank_counts.values() if c == 2)
        if num_pairs >= 2:
            if outs == 0:
                outs += 4
                draw_type = 'two_pair_to_fh'
        
        return outs, draw_type
    
    @staticmethod
    def calculate_equity(outs, streets_remaining):
        "calculate winning equity based on outs and remaining streets"
        if streets_remaining >= 2:  
            equity = min(outs * 4, 100) / 100.0
        elif streets_remaining == 1:  
            equity = min(outs * 2, 100) / 100.0
        else:
            equity = 0.0
        
        return equity
    
    @staticmethod
    def calculate_pot_odds(continue_cost, pot_total):
        if continue_cost == 0:
            return 0.0
        
        # investment need vs possible total pot after call
        pot_odds = continue_cost / (pot_total + continue_cost)
        return pot_odds
    
    @staticmethod
    def calculate_ev(equity, continue_cost, pot_total):
        """EV"""
        total_pot_if_win = pot_total + continue_cost
        ev = (equity * total_pot_if_win) - ((1 - equity) * continue_cost)
        return ev
    
    @staticmethod
    def should_call_mathematically(equity, pot_odds):
        """数学上是否应该call"""
        required_equity = pot_odds
        return equity > required_equity


class OpponentModel:
    def __init__(self, window_size=60):
        self.window_size = window_size
        self.vpip_history = deque(maxlen=window_size)
        self.pfr_history = deque(maxlen=window_size)
        self.fold_to_raise_history = deque(maxlen=window_size)
        self.postflop_aggression = deque(maxlen=window_size)
        self.opponent_type = 'unknown'
        self.confidence = 0.0
    
    def record_preflop_action(self, action_type, is_voluntary):
        if is_voluntary:
            self.vpip_history.append(action_type in ['call', 'raise'])
            self.pfr_history.append(action_type == 'raise')
    
    def record_postflop_action(self, action_type, faced_bet):
        if faced_bet:
            self.fold_to_raise_history.append(action_type == 'fold')
            self.postflop_aggression.append(action_type == 'raise')
    
    def end_hand(self):
        if len(self.vpip_history) < 10:
            self.opponent_type = 'unknown'
            self.confidence = 0.0
            return
        
        vpip = sum(self.vpip_history) / len(self.vpip_history)
        pfr = sum(self.pfr_history) / len(self.pfr_history) if self.pfr_history else 0
        fold_to_raise = (sum(self.fold_to_raise_history) / len(self.fold_to_raise_history) 
                        if self.fold_to_raise_history else 0.5)
        
        if vpip > 0.70:
            self.opponent_type = 'FISH' if pfr < 0.50 else 'LAG'
        elif vpip < 0.25:
            self.opponent_type = 'NITY'
        elif pfr > 0.40:
            self.opponent_type = 'TAG'
        else:
            self.opponent_type = 'BALANCED'
        
        if fold_to_raise > 0.75:
            self.opponent_type += '_WEAK'
        elif fold_to_raise < 0.20:
            self.opponent_type += '_STICKY'
        
        self.confidence = min(1.0, len(self.vpip_history) / self.window_size)
    
    def get_exploit_adjustments(self):
        if self.confidence < 0.25:
            return None
        
        opp = self.opponent_type
        adjustments = {
            'bluff_more': False,
            'value_bet_bigger': False,
            'call_lighter': False,
            'fold_more': False
        }
        
        if 'FISH' in opp:
            adjustments['value_bet_bigger'] = True
            adjustments['fold_more'] = True
        elif 'NITY' in opp or 'WEAK' in opp:
            adjustments['bluff_more'] = True
        elif 'LAG' in opp:
            adjustments['call_lighter'] = True
        
        if 'STICKY' in opp:
            adjustments['bluff_more'] = False
        
        return adjustments
    
    def get_stats(self):
        if not self.vpip_history:
            return None
        
        return {
            'vpip': sum(self.vpip_history) / len(self.vpip_history),
            'pfr': sum(self.pfr_history) / len(self.pfr_history) if self.pfr_history else 0,
            'fold_to_raise': (sum(self.fold_to_raise_history) / len(self.fold_to_raise_history) 
                             if self.fold_to_raise_history else 0.5),
            'type': self.opponent_type,
            'confidence': self.confidence
        }
    
class Player(Bot):
    def __init__(self):
        self.RANK_MAP = {
            "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
            "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14
        }
        
        self.poker_math = PokerMath()
        self.opponent_model = OpponentModel(window_size=60)
        self.hands_played = 0
        self.exploit_threshold = 10
        
        # Bankroll protection
        self.LOCK_THRESHOLD = 150
        self.SECURE_THRESHOLD = 300
        
        print("✓ EV-Based Bot + Probability + Exploitation + Position")
    
    def handle_new_round(self, game_state, round_state, active):
        self.hands_played += 1
        self.current_bankroll = game_state.bankroll
        
        if self.hands_played % 50 == 0:
            stats = self.opponent_model.get_stats()
            print(f"\n=== Hand {self.hands_played} | Bankroll: {self.current_bankroll} ===")
            if stats:
                print(f"对手: {stats['type']} (置信: {stats['confidence']:.2f})")
    
    def handle_round_over(self, game_state, terminal_state, active):
        self.opponent_model.end_hand()
    
    def get_action(self, game_state, round_state, active):
        legal_actions = round_state.legal_actions()
        street = round_state.street
        my_cards = round_state.hands[active]
        board_cards = round_state.board
        my_pip = round_state.pips[active]
        opp_pip = round_state.pips[1-active]
        continue_cost = opp_pip - my_pip
        pot_total = my_pip + opp_pip
        
        # Bankroll Protection
        bankroll = game_state.bankroll
        remaining_rounds = NUM_ROUNDS - game_state.round_num
        
        if remaining_rounds < 100 and bankroll >= self.SECURE_THRESHOLD:
            if FoldAction in legal_actions:
                return FoldAction()
            elif CheckAction in legal_actions:
                return CheckAction()
        
        if bankroll >= self.LOCK_THRESHOLD:
            if street == 0:
                strength = self._evaluate_preflop_strength(my_cards)
                if strength < 0.75 and FoldAction in legal_actions:
                    return FoldAction()
        
        # DISCARD
        if DiscardAction in legal_actions:
            return self._handle_discard(my_cards, board_cards, active)
        
        if len(legal_actions) == 1:
            if CheckAction in legal_actions:
                return CheckAction()
            elif CallAction in legal_actions:
                return CallAction()
            else:
                return list(legal_actions)[0]()
        
        # PREFLOP
        if street == 0:
            return self._handle_preflop(round_state, active, my_cards, continue_cost, pot_total)
        
        # POSTFLOP
        return self._handle_postflop_ev(round_state, active, my_cards, board_cards, 
                                       continue_cost, pot_total, street)
    
    def _handle_preflop(self, round_state, active, my_cards, continue_cost, pot_total):

        hand_ranks = [self.RANK_MAP[c[0]] for c in my_cards]
        hand_suits = [c[1] for c in my_cards]
        ranks_sorted = sorted(hand_ranks, reverse=True)
        
        strength = self._calculate_preflop_strength(hand_ranks, hand_suits, ranks_sorted)
        
        is_top20 = strength >= 0.60
        in_position = (active == 0)
        
        exploit_adjustments = None
        if self.hands_played >= self.exploit_threshold:
            exploit_adjustments = self.opponent_model.get_exploit_adjustments()
        
        legal_actions = round_state.legal_actions()
        
        if continue_cost > 0:
            if is_top20:
                # Top 20% - aggressive
                if RaiseAction in legal_actions and random.random() < 0.75:
                    min_raise, max_raise = round_state.raise_bounds()
                    size_factor = 0.6 + (strength - 0.60) * 0.8
                    target = int(min_raise + (max_raise - min_raise) * size_factor * 0.5)
                    target = max(min_raise, min(target, max_raise))
                    return RaiseAction(target)
                if CallAction in legal_actions:
                    return CallAction()
                return CheckAction() if CheckAction in legal_actions else FoldAction()
            
            else:
                #   Not Top 20% - cautious
                if not in_position:
                    # BB - conservative
                    if strength >= 0.40:
                        pot_odds = continue_cost / (pot_total + continue_cost) if pot_total > 0 else 0
                        if pot_odds <= 0.35 and CallAction in legal_actions:
                            return CallAction()
                    
                    if FoldAction in legal_actions:
                        return FoldAction()
                    return CheckAction() if CheckAction in legal_actions else CallAction()
                
                else:
                    # Dealer - random bluff
                    if random.random() < 0.05 and RaiseAction in legal_actions:
                        min_raise, max_raise = round_state.raise_bounds()
                        return RaiseAction(min_raise)
                    
                    if strength >= 0.35 and CallAction in legal_actions:
                        return CallAction()
                    
                    if FoldAction in legal_actions:
                        return FoldAction()
                    return CheckAction() if CheckAction in legal_actions else CallAction()
        
        else:
            if is_top20:
                if RaiseAction in legal_actions and random.random() < 0.90:
                    min_raise, max_raise = round_state.raise_bounds()
                    if strength > 0.75:
                        target = int((min_raise + max_raise) * 0.5)
                    else:
                        target = int((min_raise + max_raise) * 0.35)
                    target = max(min_raise, min(target, max_raise))
                    return RaiseAction(target)
                if CheckAction in legal_actions:
                    return CheckAction()
                return CallAction()
            
            else:
                if in_position:
                    if strength >= 0.45 and RaiseAction in legal_actions:
                        if random.random() < 0.50:
                            min_raise, max_raise = round_state.raise_bounds()
                            return RaiseAction(min_raise)
                    
                    if random.random() < 0.05 and RaiseAction in legal_actions:
                        min_raise, max_raise = round_state.raise_bounds()
                        return RaiseAction(min_raise)
                
                if CheckAction in legal_actions:
                    return CheckAction()
                return CallAction()
    
    def _handle_postflop_ev(self, round_state, active, my_cards, board_cards, 
                           continue_cost, pot_total, street):
      
        all_cards = list(my_cards) + list(board_cards)
        all_ranks = [self.RANK_MAP[c[0]] for c in all_cards]
        all_suits = [c[1] for c in all_cards]
        
        bucket, made_hand_strength = self._evaluate_postflop(all_ranks, all_suits)
        
        in_position = (active == 0)
        legal_actions = round_state.legal_actions()
        my_pip = round_state.pips[active]
        opp_pip = round_state.pips[1-active]
        
        # === calculate Outs & Equity ===
        outs, draw_type = self.poker_math.count_outs(my_cards, board_cards, self.RANK_MAP)
        
        if street == 1:  # Flop
            streets_remaining = 2  # Turn + River
        elif street == 2:  # Turn
            streets_remaining = 1  # River
        else:  # River
            streets_remaining = 0
        
        draw_equity = self.poker_math.calculate_equity(outs, streets_remaining)
        
        if draw_type:
            total_equity = max(made_hand_strength, draw_equity)
        else:
            total_equity = made_hand_strength
        
        # Exploitation
        exploit_adjustments = None
        if self.hands_played >= self.exploit_threshold:
            exploit_adjustments = self.opponent_model.get_exploit_adjustments()
        
        # === decision logic ===
        
        if continue_cost == 0:

            if bucket in ["nuts", "very-strong", "strong"]:
                if RaiseAction in legal_actions:
                    bet_prob = 0.95 if bucket == "nuts" else 0.85
                    if random.random() < bet_prob:
                        min_raise, max_raise = round_state.raise_bounds()
                        multiplier = 1.2 if bucket == "nuts" else 1.0 if bucket == "very-strong" else 0.8
                        pot_bet = int(pot_total * 0.75 * multiplier)
                        target = my_pip + pot_bet
                        target = max(min_raise, min(target, max_raise))
                        return RaiseAction(target)
                return CheckAction() if CheckAction in legal_actions else FoldAction()
            
            elif draw_type and outs >= 8: 
                if in_position and RaiseAction in legal_actions:
                    bluff_prob = min(draw_equity * 1.5, 0.60)
                    if random.random() < bluff_prob:
                        min_raise, max_raise = round_state.raise_bounds()
                        return RaiseAction(min_raise)
                return CheckAction() if CheckAction in legal_actions else FoldAction()
            
            # semi-strong
            elif bucket in ["medium-strong", "medium"]:
                if in_position and RaiseAction in legal_actions:
                    bluff_prob = 0.30
                    if exploit_adjustments and exploit_adjustments['bluff_more']:
                        bluff_prob = 0.50
                    if random.random() < bluff_prob:
                        min_raise, max_raise = round_state.raise_bounds()
                        return RaiseAction(min_raise)
                return CheckAction() if CheckAction in legal_actions else FoldAction()
            
            # weak card
            else:
                if in_position and random.random() < 0.05 and RaiseAction in legal_actions:
                    min_raise, max_raise = round_state.raise_bounds()
                    return RaiseAction(min_raise)
                return CheckAction() if CheckAction in legal_actions else FoldAction()
        
        else:
 
            pot_odds = self.poker_math.calculate_pot_odds(continue_cost, pot_total)
            ev = self.poker_math.calculate_ev(total_equity, continue_cost, pot_total)
            should_call_math = self.poker_math.should_call_mathematically(total_equity, pot_odds)

            if bucket in ["nuts", "very-strong", "strong"]:
                if RaiseAction in legal_actions:
                    raise_prob = 0.85 if bucket in ["nuts", "very-strong"] else 0.60
                    if random.random() < raise_prob:
                        min_raise, max_raise = round_state.raise_bounds()
                        target = opp_pip + int(pot_total * 1.0)
                        target = max(min_raise, min(target, max_raise))
                        return RaiseAction(target)
                if CallAction in legal_actions:
                    return CallAction()
                return CheckAction() if CheckAction in legal_actions else FoldAction()

            elif draw_type:
                if should_call_math:
                    # EV > 0，call
                    if CallAction in legal_actions:
                        print(f"  [Draw Call] Outs:{outs} Equity:{total_equity:.2%} PotOdds:{pot_odds:.2%} EV:+{ev:.1f}")
                        return CallAction()
                else:
                    # EV < 0，fold（
                    if in_position and outs >= 8 and random.random() < 0.15:
                        if RaiseAction in legal_actions:
                            min_raise, max_raise = round_state.raise_bounds()
                            return RaiseAction(min_raise)
                    
                    if FoldAction in legal_actions:
                        return FoldAction()
                    return CheckAction() if CheckAction in legal_actions else CallAction()

            elif bucket in ["medium-strong", "medium"]:
                adjusted_equity = total_equity
                if exploit_adjustments and exploit_adjustments['call_lighter']:
                    adjusted_equity *= 1.2
                
                if adjusted_equity > pot_odds:
                    if CallAction in legal_actions:
                        return CallAction()
                
                if FoldAction in legal_actions:
                    return FoldAction()
                return CheckAction() if CheckAction in legal_actions else CallAction()

            else:
                if pot_odds <= 0.20 and random.random() < 0.10:
                    if CallAction in legal_actions:
                        return CallAction()
                
                if FoldAction in legal_actions:
                    return FoldAction()
                return CheckAction() if CheckAction in legal_actions else CallAction()
        
        # Fallback
        if CheckAction in legal_actions:
            return CheckAction()
        elif CallAction in legal_actions:
            return CallAction()
        elif FoldAction in legal_actions:
            return FoldAction()
        else:
            return list(legal_actions)[0]()
    
    def _handle_discard(self, my_cards, board_cards, active):
        """Discard"""
        hand_ranks = [self.RANK_MAP[c[0]] for c in my_cards]
        hand_suits = [c[1] for c in my_cards]
        board_ranks = [self.RANK_MAP[c[0]] for c in board_cards]
        board_suits = [c[1] for c in board_cards]
        
        keep_values = []
        for i in range(len(my_cards)):
            val = 0.0
            r = hand_ranks[i]
            s = hand_suits[i]

            pair_count = hand_ranks.count(r)
            if pair_count == 2:
                val += 12.0
            elif pair_count == 3:
                val += 15.0

            board_pair_count = board_ranks.count(r)
            if board_pair_count >= 2:
                val += 10.0
            elif board_pair_count == 1:
                val += 4.0

            my_suit_count = hand_suits.count(s)
            board_suit_count = board_suits.count(s)
            total_suit = my_suit_count + board_suit_count
            if total_suit >= 4:
                val += 8.0
            elif total_suit == 3:
                val += 4.0

            all_ranks = hand_ranks + board_ranks
            if r == 14:
                all_ranks.append(1)
            unique_ranks = sorted(set(all_ranks))
            max_straight_draw = 0
            for base in unique_ranks:
                window = [x for x in unique_ranks if base <= x < base + 5]
                max_straight_draw = max(max_straight_draw, len(window))
            if max_straight_draw >= 4:
                contributes = False
                for base in unique_ranks:
                    if base <= r < base + 5:
                        contributes = True
                        break
                if r == 14 and (1 in unique_ranks or 2 in unique_ranks):
                    contributes = True
                if contributes:
                    val += 6.0

            if r == 14:
                val += 5.0
            elif r >= 12:
                val += 3.0
            elif r >= 10:
                val += 1.5

            keep_values.append(val)

        discard_idx = keep_values.index(min(keep_values))
        return DiscardAction(discard_idx)
    
    def _calculate_preflop_strength(self, hand_ranks, hand_suits, ranks_sorted):
        strength = 0.0
        
        if len(set(hand_ranks)) == 1:
            strength = 0.95
        elif len(set(hand_ranks)) == 2:
            pair_rank = max([r for r in hand_ranks if hand_ranks.count(r) == 2])
            kicker = max([r for r in hand_ranks if r != pair_rank])
            strength = 0.55 + (pair_rank / 14) * 0.25 + (kicker / 14) * 0.05
        else:
            top2_sum = ranks_sorted[0] + ranks_sorted[1]
            if ranks_sorted[0] == 14:
                if ranks_sorted[1] >= 12:
                    strength = 0.50 + (ranks_sorted[1] - 12) * 0.05
                elif ranks_sorted[1] >= 10:
                    strength = 0.40 + (ranks_sorted[1] - 10) * 0.05
                else:
                    strength = 0.25 + (ranks_sorted[1] / 14) * 0.10
            elif top2_sum >= 24:
                strength = 0.40
            elif top2_sum >= 22:
                strength = 0.32
            else:
                strength = (top2_sum / 28) * 0.30
            
            max_suit_count = max(hand_suits.count(s) for s in ['s','h','d','c'])
            if max_suit_count == 3:
                strength += 0.12
            elif max_suit_count == 2:
                strength += 0.06
            
            gaps = [ranks_sorted[i] - ranks_sorted[i+1] for i in range(len(ranks_sorted) - 1)]
            if all(g <= 1 for g in gaps):
                strength += 0.10
            elif all(g <= 2 for g in gaps):
                strength += 0.05
            
            strength = min(strength, 1.0)
        
        return strength
    
    def _evaluate_preflop_strength(self, my_cards):
        hand_ranks = [self.RANK_MAP[c[0]] for c in my_cards]
        hand_suits = [c[1] for c in my_cards]
        ranks_sorted = sorted(hand_ranks, reverse=True)
        return self._calculate_preflop_strength(hand_ranks, hand_suits, ranks_sorted)
    
    def _evaluate_postflop(self, all_ranks, all_suits):
        rank_counts = {}
        for r in all_ranks:
            rank_counts[r] = rank_counts.get(r, 0) + 1
        sorted_counts = sorted(rank_counts.values(), reverse=True)
        
        suit_counts = {'s': 0, 'h': 0, 'd': 0, 'c': 0}
        for s in all_suits:
            suit_counts[s] += 1
        max_suit_count = max(suit_counts.values())
        has_flush = max_suit_count >= 5
        
        unique_ranks = sorted(set(all_ranks))
        if 14 in unique_ranks:
            unique_ranks = [1] + unique_ranks
        has_straight = False
        straight_run = 1
        for i in range(1, len(unique_ranks)):
            if unique_ranks[i] == unique_ranks[i-1] + 1:
                straight_run += 1
                if straight_run >= 5:
                    has_straight = True
                    break
            else:
                straight_run = 1
        
        if has_flush and has_straight:
            return "nuts", 0.95
        elif sorted_counts and sorted_counts[0] == 4:
            return "nuts", 0.92
        elif has_flush or has_straight:
            return "very-strong", 0.85
        elif len(sorted_counts) >= 2 and sorted_counts[0] == 3 and sorted_counts[1] >= 2:
            return "very-strong", 0.82
        elif sorted_counts and sorted_counts[0] == 3:
            return "strong", 0.70
        elif len(sorted_counts) >= 2 and sorted_counts[0] == 2 and sorted_counts[1] == 2:
            pairs = sorted([r for r, c in rank_counts.items() if c == 2], reverse=True)
            if pairs[0] >= 10:
                return "strong", 0.65
            else:
                return "medium-strong", 0.55
        elif sorted_counts and sorted_counts[0] == 2:
            pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
            if pair_rank >= 11:
                return "medium-strong", 0.50
            elif pair_rank >= 8:
                return "medium", 0.40
            else:
                return "medium-weak", 0.32
        else:
            has_flush_draw = max_suit_count == 4
            has_straight_draw = any(
                len([x for x in unique_ranks if base <= x <= base + 4]) >= 4
                for base in unique_ranks
            )
            
            if has_flush_draw or has_straight_draw:
                return "draw", 0.35
            else:
                return "weak", 0.15


if __name__ == '__main__':
    run_bot(Player(), parse_args())