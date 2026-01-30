"""
Execution Engine for IBKR Premarket Strategy
Handles aggressive limit orders, timeouts, and state tracking.
"""
import threading
import time
import logging
from datetime import datetime
from typing import Dict, Optional, List, Set, Tuple
from ibapi.contract import Contract
from ibapi.order import Order
import strategy_config as config

class ExecutionEngine:
    def __init__(self, tws_app, account: str):
        self.tws_app = tws_app
        self.account = account
        
        # State: symbol -> {status, entry_price, stop_price, R, shares, entry_time, order_id, ...}
        self.positions: Dict[str, Dict] = {}
        self.order_to_symbol: Dict[int, str] = {}
        self.trade_history: List[Dict] = []
        self.blacklist: Set[str] = set()
        self.consecutive_losses: int = 0
        
        self.lock = threading.Lock()
        
        # Callbacks
        self.tws_app.order_status_callbacks.append(self._on_order_status)
        self.tws_app.error_callbacks = getattr(self.tws_app, 'error_callbacks', [])
        self.tws_app.error_callbacks.append(self._on_tws_error)

    def _create_contract(self, symbol: str) -> Contract:
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        return contract

    def _on_tws_error(self, reqId: int, errorCode: int, errorString: str):
        if errorCode == 201: # Order rejected
            symbol = self.order_to_symbol.get(reqId)
            if symbol:
                logging.error(f"[EXEC] {symbol} REJECTED: {errorString}")
                with self.lock:
                    self.blacklist.add(symbol)
                    if symbol in self.positions:
                        self._cleanup_position(symbol, "REJECTED")

    def _on_order_status(self, orderId, status, filled, remaining, avgFillPrice, parentId):
        with self.lock:
            symbol = self.order_to_symbol.get(orderId)
            if not symbol or symbol not in self.positions:
                return
                
            pos = self.positions[symbol]
            
            if status == 'Filled':
                if pos['status'] == 'SUBMITTING':
                    pos['status'] = 'IN_TRADE'
                    pos['actual_entry_price'] = avgFillPrice
                    pos['filled_shares'] = filled
                    logging.info(f"[EXEC] >>> {symbol} FILLED at ${avgFillPrice:.2f} <<<")
                elif pos['status'] == 'EXITING':
                    logging.info(f"[EXEC] >>> {symbol} CLOSED at ${avgFillPrice:.2f} <<<")
                    self._record_trade(symbol, "CLOSED", avgFillPrice)
                    self._cleanup_position(symbol)

            elif status in ['Cancelled', 'Inactive', 'ApiCancelled']:
                if pos['status'] == 'SUBMITTING':
                    if filled > 0:
                        logging.info(f"[EXEC] {symbol} PARTIAL FILL: {filled} shares at ${avgFillPrice:.2f}")
                        pos['status'] = 'IN_TRADE'
                        pos['actual_entry_price'] = avgFillPrice
                        pos['filled_shares'] = filled
                    else:
                        logging.info(f"[EXEC] {symbol} entry order CANCELLED/INACTIVE")
                        self._cleanup_position(symbol)
                elif pos['status'] == 'EXITING':
                    # If exit order is cancelled, we might need to retry or it's a major issue
                    logging.warning(f"[EXEC] WARNING: Exit order for {symbol} was {status}")

    def _cleanup_position(self, symbol: str, reason: str = ""):
        if symbol in self.positions:
            pos = self.positions[symbol]
            # Clean up order mapping
            oids = [oid for oid, sym in self.order_to_symbol.items() if sym == symbol]
            for oid in oids:
                if oid in self.order_to_symbol: del self.order_to_symbol[oid]
            del self.positions[symbol]

    def _record_trade(self, symbol: str, type: str, exit_price: float):
        pos = self.positions[symbol]
        entry_price = pos.get('actual_entry_price', pos['entry_price'])
        shares = pos.get('filled_shares', pos['shares'])
        pnl = (exit_price - entry_price) * shares
        
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
            
        self.trade_history.append({
            'symbol': symbol,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'shares': shares,
            'pnl': pnl,
            'time': datetime.now(),
            'exit_reason': pos.get('exit_reason', 'UNKNOWN')
        })

    def execute_entry(self, symbol: str, ask_price: float, stop_price: float, R: float) -> bool:
        """Place an aggressive limit buy order with timeout."""
        with self.lock:
            if symbol in self.positions or symbol in self.blacklist:
                return False
            
            if self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
                logging.warning(f"[EXEC] Kill switch active: {self.consecutive_losses} consecutive losses.")
                return False

            limit_price = round(ask_price + config.ENTRY_OFFSET, 2)
            # Ensure integer shares for compatibility with older API versions
            shares = int(config.INVESTMENT_PER_TRADE // limit_price)
            if shares <= 0: return False
            
            order_id = self.tws_app.next_order_id
            self.tws_app.next_order_id += 1
            
            contract = self._create_contract(symbol)
            order = Order()
            order.orderId = order_id
            order.action = "BUY"
            order.orderType = "LMT"
            order.lmtPrice = limit_price
            order.totalQuantity = shares
            order.account = self.account
            order.outsideRth = True
            order.transmit = True
            
            self.positions[symbol] = {
                'status': 'SUBMITTING',
                'entry_price': limit_price,
                'stop_price': stop_price,
                'R': R,
                'shares': shares,
                'entry_time': datetime.now(),
                'order_id': order_id
            }
            self.order_to_symbol[order_id] = symbol
            
            self.tws_app.placeOrder(order_id, contract, order)
            logging.info(f"[EXEC] Entry submitted for {symbol}: {shares} @ ${limit_price}")
            
            # Start timeout thread
            threading.Thread(target=self._handle_entry_timeout, args=(symbol, order_id), daemon=True).start()
            return True

    def _handle_entry_timeout(self, symbol: str, order_id: int):
        time.sleep(config.ENTRY_TIMEOUT_MS / 1000.0)
        with self.lock:
            if symbol in self.positions and self.positions[symbol]['status'] == 'SUBMITTING':
                logging.info(f"[EXEC] Timeout reached for {symbol} entry. Cancelling.")
                self.tws_app.cancelOrder(order_id)
                # Status will be updated via _on_order_status

    def execute_exit(self, symbol: str, price: float, reason: str):
        """Exit position with a market order (or aggressive limit)."""
        with self.lock:
            if symbol not in self.positions or self.positions[symbol]['status'] != 'IN_TRADE':
                return
            
            pos = self.positions[symbol]
            pos['status'] = 'EXITING'
            pos['exit_reason'] = reason
            
            contract = self._create_contract(symbol)
            order = Order()
            order.action = "SELL"
            order.orderType = "MKT" # In premarket MKT might be rejected, use aggressive LMT
            # TWS often accepts MKT in premarket if routed correctly, but LMT is safer
            order.orderType = "LMT"
            order.lmtPrice = round(price * 0.98, 2) # 2% slippage allowance for fast exit
            order.totalQuantity = pos['filled_shares']
            order.account = self.account
            order.outsideRth = True
            order.transmit = True
            
            order_id = self.tws_app.next_order_id
            self.tws_app.next_order_id += 1
            self.order_to_symbol[order_id] = symbol
            
            self.tws_app.placeOrder(order_id, contract, order)
            logging.info(f"[EXEC] Exit submitted for {symbol} ({reason})")

    def get_position(self, symbol: str) -> Optional[Dict]:
        with self.lock:
            return self.positions.get(symbol)
