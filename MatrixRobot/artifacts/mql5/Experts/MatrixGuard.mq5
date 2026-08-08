//+------------------------------------------------------------------+
//|                                               MatrixGuard.mq5    |
//| Matrix Robot — local protective layer (does NOT open trades)     |
//| Role: watch Bridge heartbeat + equity DD; emergency flatten.     |
//| Brain/Bridge remain the decision & execution path.               |
//+------------------------------------------------------------------+
#property copyright "Matrix Robot"
#property link      "https://github.com/anasalraji61-maker/MATRIX--ROBOT-"
#property version   "1.00"
#property strict
#property description "Protective EA only. No entries. Compiles in MetaEditor (F7)."

#include <Trade/Trade.mqh>

//---------------- inputs ----------------
input string InpBridgeUrl           = "http://127.0.0.1:5555/version"; // Primary Bridge ping URL
input string InpBridgeUrlFallback   = "http://localhost:5555/version";  // Fallback if 127.0.0.1 blocked
input int    InpCheckSeconds        = 10;     // Check interval (seconds)
input int    InpBridgeFailLimit     = 3;      // Consecutive Bridge failures before alert/action
input double InpMaxDailyDDPercent   = 4.0;    // Max daily equity drawdown % from day start
input double InpMaxTotalDDPercent   = 9.0;    // Max equity drawdown % from balance
input bool   InpCloseOnBridgeDown   = false;  // Close all positions if Bridge dead (default: alert only)
input bool   InpCloseOnDailyDD      = true;   // Close all if daily DD breached
input bool   InpCloseOnTotalDD      = true;   // Close all if total DD breached
input bool   InpEnableAlerts        = true;   // Popup / Push alerts
input long   InpMagicTag            = 911001; // Marker for log (does not filter closes)

//---------------- state ----------------
CTrade   g_trade;
datetime g_lastCheck      = 0;
int      g_bridgeFails    = 0;
bool     g_bridgeOk       = false;
bool     g_lockout        = false;
string   g_lockReason     = "";
double   g_dayStartEquity = 0.0;
int      g_dayStamp       = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   g_trade.SetAsyncMode(false);
   g_trade.SetDeviationInPoints(30);
   ResetDayBaseline();
   EventSetTimer(MathMax(3, InpCheckSeconds));
   PrintFormat("MatrixGuard started | Bridge=%s | DailyDD=%.2f%% TotalDD=%.2f%%",
               InpBridgeUrl, InpMaxDailyDDPercent, InpMaxTotalDDPercent);
   Comment(BuildPanel());
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
}

//+------------------------------------------------------------------+
void OnTick()
{
   // Protective only — no entries. Periodic work is in OnTimer.
   Comment(BuildPanel());
}

//+------------------------------------------------------------------+
void OnTimer()
{
   if(TimeCurrent() - g_lastCheck < InpCheckSeconds)
      return;
   g_lastCheck = TimeCurrent();

   ResetDayBaseline();
   CheckBridge();
   CheckDrawdown();
   Comment(BuildPanel());
}

//+------------------------------------------------------------------+
void ResetDayBaseline()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int stamp = dt.year * 10000 + dt.mon * 100 + dt.day;
   if(stamp != g_dayStamp)
   {
      g_dayStamp = stamp;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(g_dayStartEquity <= 0.0)
         g_dayStartEquity = AccountInfoDouble(ACCOUNT_BALANCE);
      g_lockout = false;
      g_lockReason = "";
      PrintFormat("MatrixGuard: new day baseline equity=%.2f", g_dayStartEquity);
   }
}

//+------------------------------------------------------------------+
bool PingBridgeUrl(const string url, int &out_code, int &out_err)
{
   char   result[];
   char   data[];
   string result_headers;
   string headers = "User-Agent: MatrixGuard/1.0\r\nAccept: */*\r\n";

   ResetLastError();
   out_code = WebRequest("GET", url, headers, 5000, data, result, result_headers);
   out_err = GetLastError();
   // Success: HTTP 200, or body received with a non-negative transport code.
   if(out_code == 200)
      return true;
   // Some builds return -1 on deny/timeout; treat only clear 200 as OK.
   return false;
}

void CheckBridge()
{
   int code = 0, err = 0;
   bool ok = PingBridgeUrl(InpBridgeUrl, code, err);
   string used = InpBridgeUrl;

   if(!ok && StringLen(InpBridgeUrlFallback) > 0 && InpBridgeUrlFallback != InpBridgeUrl)
   {
      ok = PingBridgeUrl(InpBridgeUrlFallback, code, err);
      used = InpBridgeUrlFallback;
   }

   if(ok)
   {
      g_bridgeFails = 0;
      g_bridgeOk = true;
      return;
   }

   g_bridgeFails++;
   g_bridgeOk = false;
   PrintFormat("MatrixGuard: Bridge ping failed url=%s code=%d err=%d fails=%d", used, code, err, g_bridgeFails);

   if(g_bridgeFails < InpBridgeFailLimit)
      return;

   string reason = StringFormat("Bridge down (%d fails) last=%s", g_bridgeFails, used);
   Notify(reason);

   if(InpCloseOnBridgeDown)
      EmergencyFlatten(reason);
}

//+------------------------------------------------------------------+
void CheckDrawdown()
{
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(equity <= 0.0 || balance <= 0.0 || g_dayStartEquity <= 0.0)
      return;

   double dailyDd = 100.0 * (g_dayStartEquity - equity) / g_dayStartEquity;
   double totalDd = 100.0 * (balance - equity) / balance;
   if(totalDd < 0.0) totalDd = 0.0;
   if(dailyDd < 0.0) dailyDd = 0.0;

   if(InpCloseOnDailyDD && dailyDd >= InpMaxDailyDDPercent)
   {
      string reason = StringFormat("Daily DD %.2f%% >= %.2f%%", dailyDd, InpMaxDailyDDPercent);
      EmergencyFlatten(reason);
      return;
   }

   if(InpCloseOnTotalDD && totalDd >= InpMaxTotalDDPercent)
   {
      string reason = StringFormat("Total DD %.2f%% >= %.2f%%", totalDd, InpMaxTotalDDPercent);
      EmergencyFlatten(reason);
   }
}

//+------------------------------------------------------------------+
void EmergencyFlatten(const string reason)
{
   if(g_lockout && g_lockReason == reason)
      return;

   g_lockout = true;
   g_lockReason = reason;
   Notify("EMERGENCY FLATTEN: " + reason);

   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;

      // Close ALL account positions — this is a hard safety net.
      if(!g_trade.PositionClose(ticket))
         PrintFormat("MatrixGuard: close failed ticket=%I64u retcode=%u", ticket, g_trade.ResultRetcode());
      else
         PrintFormat("MatrixGuard: closed ticket=%I64u", ticket);
   }
}

//+------------------------------------------------------------------+
void Notify(const string msg)
{
   Print("MatrixGuard: ", msg);
   if(InpEnableAlerts)
   {
      Alert("MatrixGuard: ", msg);
      SendNotification("MatrixGuard: " + msg);
   }
}

//+------------------------------------------------------------------+
string BuildPanel()
{
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double dailyDd = 0.0;
   double totalDd = 0.0;
   if(g_dayStartEquity > 0.0)
      dailyDd = MathMax(0.0, 100.0 * (g_dayStartEquity - equity) / g_dayStartEquity);
   if(balance > 0.0)
      totalDd = MathMax(0.0, 100.0 * (balance - equity) / balance);

   string bridge = g_bridgeOk ? "OK" : StringFormat("DOWN (%d)", g_bridgeFails);
   string lock   = g_lockout ? ("LOCK: " + g_lockReason) : "armed";

   return StringFormat(
      "MatrixGuard (protective only)\nBridge: %s\nDailyDD: %.2f%% / %.2f%%\nTotalDD: %.2f%% / %.2f%%\nPositions: %d\nStatus: %s\n",
      bridge,
      dailyDd, InpMaxDailyDDPercent,
      totalDd, InpMaxTotalDDPercent,
      PositionsTotal(),
      lock
   );
}

//+------------------------------------------------------------------+
