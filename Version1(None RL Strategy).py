'''
None RL pokerbot
'''
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, DiscardAction
from skeleton.states import GameState, TerminalState, RoundState
from skeleton.states import NUM_ROUNDS, STARTING_STACK, BIG_BLIND, SMALL_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot
import random


class Player(Bot):

    def __init__(self):
        self.RANK_MAP = {
            "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
            "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14
        }

    def handle_new_round(self, game_state, round_state, active):
        my_bankroll = game_state.bankroll
        game_clock = game_state.game_clock
        round_num = game_state.round_num
        my_cards = round_state.hands[active]
        big_blind = bool(active)

    def handle_round_over(self, game_state, terminal_state, active):
        my_delta = terminal_state.deltas[active]
        previous_state = terminal_state.previous_state
        street = previous_state.street
        my_cards = previous_state.hands[active]
        opp_cards = previous_state.hands[1-active]

    def get_action(self, game_state, round_state, active):
        legal_actions = round_state.legal_actions()
        street = round_state.street
        my_cards = round_state.hands[active]
        board_cards = round_state.board
        my_pip = round_state.pips[active]
        opp_pip = round_state.pips[1-active]
        my_stack = round_state.stacks[active]
        opp_stack = round_state.stacks[1-active]
        continue_cost = opp_pip - my_pip
        my_contribution = STARTING_STACK - my_stack
        opp_contribution = STARTING_STACK - opp_stack
        pot_total = my_pip + opp_pip

        #===DISCARD PHASE===
        if DiscardAction in legal_actions:
            hand_ranks = [self.RANK_MAP[c[0]] for c in my_cards]
            hand_suits = [c[1] for c in my_cards]
            board_ranks = [self.RANK_MAP[c[0]] for c in board_cards]
            board_suits = [c[1] for c in board_cards]

            keep_values = []
            for i in range(3):
                val = 0.0
                r = hand_ranks[i]
                s = hand_suits[i]

                # Pair bonus
                pair_count = hand_ranks.count(r)
                if pair_count == 2:
                    val += 12.0
                elif pair_count == 3:
                    val += 15.0

                # Board pair synergy
                board_pair_count = board_ranks.count(r)
                if board_pair_count >= 2:
                    val += 10.0
                elif board_pair_count == 1:
                    val += 4.0

                # Flush potential
                my_suit_count = hand_suits.count(s)
                board_suit_count = board_suits.count(s)
                total_suit = my_suit_count + board_suit_count
                if total_suit >= 4:
                    val += 8.0
                elif total_suit == 3:
                    val += 4.0

                # Straight potential
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

                # High card value
                if r == 14:
                    val += 5.0
                elif r >= 12:
                    val += 3.0
                elif r >= 10:
                    val += 1.5

                keep_values.append(val)

            discard_idx = keep_values.index(min(keep_values))
            return DiscardAction(discard_idx)

        if len(legal_actions) == 1 and CheckAction in legal_actions:
            return CheckAction()

        #===PREFLOP===
        if street == 0:
            hand_ranks = [self.RANK_MAP[c[0]] for c in my_cards]
            hand_suits = [c[1] for c in my_cards]
            ranks_sorted = sorted(hand_ranks, reverse=True)
            strength = 0.0

            # Trips
            if len(set(hand_ranks)) == 1:
                strength = 0.95
            # Pair
            elif len(set(hand_ranks)) == 2:
                pair_rank = max([r for r in hand_ranks if hand_ranks.count(r) == 2])
                kicker = max([r for r in hand_ranks if r != pair_rank])
                strength = 0.55 + (pair_rank / 14) * 0.25 + (kicker / 14) * 0.05
            # High card
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

                # Suited bonus
                max_suit_count = max(hand_suits.count("s"), hand_suits.count("h"),
                                   hand_suits.count("d"), hand_suits.count("c"))
                if max_suit_count == 3:
                    strength += 0.12
                elif max_suit_count == 2:
                    strength += 0.06
                # Connected bonus
                gaps = [ranks_sorted[i] - ranks_sorted[i+1] for i in range(len(ranks_sorted) - 1)]
                if all(g <= 1 for g in gaps):
                    strength += 0.10
                elif all(g <= 2 for g in gaps):
                    strength += 0.05
                strength = min(strength, 1.0)

            # Decision logic
            if continue_cost > 0:
                pot_odds = continue_cost / (pot_total + continue_cost) if (pot_total + continue_cost) > 0 else 0

                if strength < 0.20:
                    if FoldAction in legal_actions:
                        return FoldAction()
                    return CheckAction() if CheckAction in legal_actions else CallAction()
                elif strength < 0.35:
                    if pot_odds > 0.35 and FoldAction in legal_actions:
                        return FoldAction()
                    if CallAction in legal_actions:
                        return CallAction()
                    return CheckAction() if CheckAction in legal_actions else FoldAction()
                elif strength < 0.60:
                    if CallAction in legal_actions:
                        return CallAction()
                    return CheckAction() if CheckAction in legal_actions else FoldAction()
                else:
                    if RaiseAction in legal_actions:
                        min_raise, max_raise = round_state.raise_bounds()
                        size_factor = 0.4 + (strength - 0.60) * 0.6
                        target = int(min_raise + (max_raise - min_raise) * size_factor * 0.3)
                        target = max(min_raise, min(target, max_raise))
                        return RaiseAction(target)
                    if CallAction in legal_actions:
                        return CallAction()
                    return CheckAction()
            else:
                if CheckAction in legal_actions:
                    return CheckAction()
                return CallAction()

        # ====POST-DISCARD BETTING===
        all_cards = list(my_cards) + list(board_cards)
        all_ranks = [self.RANK_MAP[c[0]] for c in all_cards]
        all_suits = [c[1] for c in all_cards]

        # Count ranks
        rank_counts = {}
        for r in all_ranks:
            rank_counts[r] = rank_counts.get(r, 0) + 1
        sorted_counts = sorted(rank_counts.values(), reverse=True)

        # Check flush
        suit_counts = {"s": 0, "h": 0, "d": 0, "c": 0}
        for s in all_suits:
            suit_counts[s] += 1
        max_suit_count = max(suit_counts.values())
        has_flush = max_suit_count >= 5

        # Check straight
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

        # Determine bucket
        if has_flush or has_straight:
            bucket = "strong"
        elif sorted_counts and sorted_counts[0] >= 3:
            bucket = "strong"
        elif len(sorted_counts) >= 2 and sorted_counts[0] == 2 and sorted_counts[1] == 2:
            bucket = "strong"
        elif sorted_counts and sorted_counts[0] == 2:
            bucket = "medium"
        else:
            has_flush_draw = max_suit_count == 4
            unique_ranks2 = sorted(set(all_ranks))
            if 14 in unique_ranks2:
                unique_ranks2 = [1] + unique_ranks2
            has_straight_draw = False
            for base in unique_ranks2:
                window = [x for x in unique_ranks2 if base <= x <= base + 4]
                if len(window) >= 4:
                    has_straight_draw = True
                    break
            if has_flush_draw or has_straight_draw:
                bucket = "medium"
            else:
                bucket = "weak"
        in_position = (active == 0)

        # Decision
        if continue_cost == 0:
            if bucket == "strong":
                if RaiseAction in legal_actions:
                    min_raise, max_raise = round_state.raise_bounds()
                    pot_bet = pot_total
                    target = my_pip + pot_bet
                    target = max(min_raise, min(target, max_raise))
                    return RaiseAction(target)
                return CheckAction() if CheckAction in legal_actions else FoldAction()
            elif bucket == "medium":
                if in_position and RaiseAction in legal_actions:
                    if random.random() < 0.35:
                        min_raise, max_raise = round_state.raise_bounds()
                        return RaiseAction(min_raise)
                return CheckAction() if CheckAction in legal_actions else FoldAction()
            else:
                return CheckAction() if CheckAction in legal_actions else FoldAction()
        else:
            pot_odds = continue_cost / (pot_total + continue_cost) if (pot_total + continue_cost) > 0 else 0
            if bucket == "strong":
                if RaiseAction in legal_actions:
                    min_raise, max_raise = round_state.raise_bounds()
                    target = opp_pip + pot_total
                    target = max(min_raise, min(target, max_raise))
                    if random.random() < 0.65:
                        return RaiseAction(target)
                if CallAction in legal_actions:
                    return CallAction()
                return CheckAction() if CheckAction in legal_actions else FoldAction()
            elif bucket == "medium":
                if pot_odds <= 0.40:
                    if CallAction in legal_actions:
                        return CallAction()
                if FoldAction in legal_actions:
                    return FoldAction()
                return CheckAction() if CheckAction in legal_actions else CallAction()
            else:
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


if __name__ == '__main__':
    run_bot(Player(), parse_args())
