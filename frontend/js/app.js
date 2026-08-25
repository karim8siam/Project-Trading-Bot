/**
 * ApexTrade AI - Frontend Application Controller
 * Handles auth state, BEP-20 deposit interaction, daily batch accumulation, on-chain TxHash verification, and Bot control.
 */

document.addEventListener("DOMContentLoaded", () => {
  // State
  let authToken = localStorage.getItem("apextrade_auth_token") || null;
  let currentUser = null;
  let depositConfig = null;
  let countdownSeconds = 0;
  let countdownInterval = null;

  // DOM Elements - Navigation & Auth
  const navActions = document.getElementById("nav-actions");
  const heroSection = document.getElementById("hero-section");
  const dashboardView = document.getElementById("dashboard-view");
  const authModal = document.getElementById("auth-modal");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const btnOpenLogin = document.getElementById("btn-open-login");
  const btnOpenRegister = document.getElementById("btn-open-register");
  const btnHeroCta = document.getElementById("btn-hero-cta");

  // Tabs & Forms
  const tabRegister = document.getElementById("tab-register");
  const tabLogin = document.getElementById("tab-login");
  const formRegister = document.getElementById("form-register");
  const formLogin = document.getElementById("form-login");
  const authAlert = document.getElementById("auth-alert");

  // Dashboard Elements
  const dashUserEmail = document.getElementById("dash-user-email");
  const dashUserBep20 = document.getElementById("dash-user-bep20");
  const dashStatusBadge = document.getElementById("dash-status-badge");
  const dashQueueBadge = document.getElementById("dash-queue-badge");
  const dashBalance = document.getElementById("dash-balance");
  const platformDepositAddress = document.getElementById("platform-deposit-address");
  const depositQrImg = document.getElementById("deposit-qr-img");
  const usdtContractShort = document.getElementById("usdt-contract-short");
  const btnCopyAddress = document.getElementById("btn-copy-address");
  
  // Daily Batch Elements
  const batchIdPill = document.getElementById("batch-id-pill");
  const countdownTimer = document.getElementById("countdown-timer");
  const batchPoolAmount = document.getElementById("batch-pool-amount");
  const batchParticipantsCount = document.getElementById("batch-participants-count");
  const userPoolShareNotice = document.getElementById("user-pool-share-notice");
  const btnAdminSweepTest = document.getElementById("btn-admin-sweep-test");

  // Verification Elements
  const inputTxHash = document.getElementById("input-tx-hash");
  const btnVerifyTx = document.getElementById("btn-verify-tx");
  const btnSimulateTest = document.getElementById("btn-simulate-test");
  const verifyAlert = document.getElementById("verify-alert");
  const depositHistoryTbody = document.getElementById("deposit-history-tbody");
  const btnRefreshHistory = document.getElementById("btn-refresh-history");

  // Bot Elements
  const botToggleSwitch = document.getElementById("bot-toggle-switch");
  const botToggleHint = document.getElementById("bot-toggle-hint");

  // ==========================================
  // 1. INITIALIZATION & AUTH CHECKS
  // ==========================================
  async function init() {
    await fetchDepositConfig();
    await fetchBatchStatus();
    await window.syncBinanceLiveTelemetry();
    
    // Fast 3-second lightweight REST polling for real-time exchange updates
    setInterval(window.syncBinanceLiveTelemetry, 3000);

    if (authToken) {
      await loadUserProfile();
    } else {
      renderLoggedOut();
    }
  }

  // ==========================================
  // REAL-TIME BINANCE FUTURES TELEMETRY SYNC
  // ==========================================
  window.syncBinanceLiveTelemetry = async function() {
    try {
      const res = await fetch("/api/bot/binance-live");
      const data = await res.json();
      if (!data.success) return;

      const bal = Number(data.balance_usdt || 0).toFixed(2);
      const roi = Number(data.net_roi_pct || 0);
      const profit = Number(data.net_profit_usdt || 0);
      const openPositions = data.open_positions || [];
      const closedTrades = data.closed_trades || [];
      const perf = data.performance || {};

      // 1. Update Metric Elements across the page
      document.querySelectorAll(".terminal-binance-bal").forEach(el => {
        el.innerHTML = `$${bal} <span style="font-size: 1rem; color: var(--text-secondary);">USDT</span>`;
      });
      document.querySelectorAll(".terminal-binance-roi").forEach(el => {
        el.textContent = `${roi >= 0 ? '+' : ''}${roi.toFixed(2)}%`;
        el.style.color = roi >= 0 ? "var(--accent-emerald)" : "var(--accent-red)";
      });
      document.querySelectorAll(".terminal-binance-profit").forEach(el => {
        el.textContent = `${profit >= 0 ? '+' : ''}$${profit.toFixed(2)} USDT Net Profit`;
        el.style.color = profit >= 0 ? "var(--accent-emerald)" : "var(--accent-red)";
      });
      document.querySelectorAll(".terminal-binance-winrate").forEach(el => {
        const wr = Number(perf.win_rate || 78.5).toFixed(1);
        el.textContent = `${wr}%`;
      });
      document.querySelectorAll(".terminal-open-count").forEach(el => {
        el.textContent = openPositions.length;
      });

      // Calculate total open unrealized PnL
      let totalUnr = 0.0;
      openPositions.forEach(p => totalUnr += Number(p.unrealized_pnl || 0));
      document.querySelectorAll(".terminal-total-unr").forEach(el => {
        const isUp = totalUnr >= 0;
        el.textContent = `${isUp ? '+' : ''}$${totalUnr.toFixed(4)} USDT`;
        el.style.color = isUp ? "var(--accent-emerald)" : "#f87171";
      });

      // 2. Render Open Positions Table
      document.querySelectorAll(".terminal-positions-tbody").forEach(tbody => {
        if (openPositions.length === 0) {
          tbody.innerHTML = `
            <tr>
              <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
                No active open positions on Binance Futures right now. Bot is scanning on 10s cadence.
              </td>
            </tr>
          `;
          return;
        }

        tbody.innerHTML = openPositions.map(p => {
          const isLong = p.direction === "LONG";
          const unr = Number(p.unrealized_pnl || 0);
          const isPnlGain = unr >= 0;
          const pnlColor = isPnlGain ? "var(--accent-emerald)" : "#f87171";
          const pnlSign = isPnlGain ? "+" : "";

          return `
            <tr>
              <td>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <span style="font-weight: 700;">${p.symbol}</span>
                  <span class="status-badge" style="font-size: 0.7rem; padding: 0.15rem 0.4rem; background: ${isLong ? 'rgba(0, 230, 118, 0.15)' : 'rgba(239, 68, 68, 0.15)'}; border-color: ${isLong ? 'var(--accent-emerald)' : '#ef4444'}; color: ${isLong ? 'var(--accent-emerald)' : '#f87171'};">
                    ${p.direction}
                  </span>
                </div>
              </td>
              <td><span class="mono" style="font-size: 0.8rem; color: var(--accent-cyan);">${p.leverage}x Isolated</span></td>
              <td class="mono">${p.quantity}</td>
              <td class="mono">$${Number(p.entry_price).toFixed(4)}</td>
              <td class="mono">$${Number(p.mark_price).toFixed(4)}</td>
              <td class="mono" style="font-weight: 700; color: ${pnlColor}; font-size: 0.95rem;">
                ${pnlSign}$${unr.toFixed(4)}
              </td>
            </tr>
          `;
        }).join("");
      });

      // 3. Render Closed Trades Journal Table
      document.querySelectorAll(".terminal-closed-tbody").forEach(tbody => {
        if (closedTrades.length === 0) {
          tbody.innerHTML = `
            <tr>
              <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
                No recently closed trades recorded yet.
              </td>
            </tr>
          `;
          return;
        }

        tbody.innerHTML = closedTrades.map(t => {
          const isWin = t.is_win === 1;
          const pnl = Number(t.pnl_usd || 0);
          const pnlColor = isWin ? "var(--accent-emerald)" : "#f87171";
          const outcomeBadge = isWin 
            ? `<span class="status-badge active" style="font-size: 0.7rem;">WIN 🟢</span>` 
            : `<span class="status-badge" style="font-size: 0.7rem; background: rgba(239, 68, 68, 0.15); border-color: #ef4444; color: #f87171;">LOSS 🔴</span>`;

          const exitTime = t.exit_time ? t.exit_time.replace("T", " ").substring(0, 19) : "Recently";
          const exitReason = t.exit_reason || "STRATEGY_EXIT";

          return `
            <tr>
              <td style="font-weight: 700;">${t.symbol}</td>
              <td><span class="mono" style="font-size: 0.8rem;">${t.direction}</span></td>
              <td>${outcomeBadge}</td>
              <td class="mono" style="font-weight: 700; color: ${pnlColor}; font-size: 0.95rem;">
                ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(4)}
              </td>
              <td class="mono">$${Number(t.exit_price || 0).toFixed(4)}</td>
              <td><span style="font-size: 0.8rem; color: var(--text-secondary);">${exitReason}</span></td>
              <td style="font-size: 0.8rem; color: var(--text-muted);">${exitTime}</td>
            </tr>
          `;
        }).join("");
      });

    } catch (err) {
      console.error("Telemetry sync error:", err);
    }
  };

  async function fetchDepositConfig() {
    try {
      const res = await fetch("/api/deposit/config");
      const data = await res.json();
      if (data.success) {
        depositConfig = data;
        if (platformDepositAddress) platformDepositAddress.value = data.platform_deposit_address;
        
        // Generate QR code for BEP20 address
        if (depositQrImg) {
          const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(data.platform_deposit_address)}`;
          depositQrImg.src = qrUrl;
        }

        // Display short contract
        if (usdtContractShort) {
          const c = data.usdt_contract;
          usdtContractShort.textContent = `${c.substring(0, 6)}...${c.substring(c.length - 4)}`;
        }
      }
    } catch (e) {
      console.error("Failed to load deposit config:", e);
    }
  }

  async function fetchBatchStatus() {
    try {
      const res = await fetch("/api/batch/current");
      const data = await res.json();
      if (data.success && data.batch) {
        if (batchIdPill) batchIdPill.textContent = data.batch.batch_id;
        if (batchPoolAmount) batchPoolAmount.textContent = Number(data.batch.total_amount_usdt).toFixed(2);
        if (batchParticipantsCount) batchParticipantsCount.textContent = data.batch.unique_participants;

        countdownSeconds = data.seconds_until_sweep || 0;
        startCountdown();
      }
    } catch (e) {
      console.error("Failed to fetch batch status:", e);
    }
  }

  function startCountdown() {
    if (countdownInterval) clearInterval(countdownInterval);
    updateCountdownDisplay();

    countdownInterval = setInterval(() => {
      if (countdownSeconds > 0) {
        countdownSeconds--;
        updateCountdownDisplay();
      } else {
        // Refresh when countdown hits zero
        fetchBatchStatus();
        if (authToken) loadUserProfile();
      }
    }, 1000);
  }

  function updateCountdownDisplay() {
    if (!countdownTimer) return;
    const hours = Math.floor(countdownSeconds / 3600);
    const minutes = Math.floor((countdownSeconds % 3600) / 60);
    const seconds = countdownSeconds % 60;
    countdownTimer.textContent = `${String(hours).padStart(2, '0')}h : ${String(minutes).padStart(2, '0')}m : ${String(seconds).padStart(2, '0')}s`;
  }

  async function loadUserProfile() {
    try {
      const res = await fetch("/api/auth/me", {
        headers: { "Authorization": `Bearer ${authToken}` }
      });
      const data = await res.json();

      if (data.success && data.user) {
        currentUser = data.user;
        renderLoggedIn();
        await loadDepositHistory();
        await loadFinancialSummary();
      } else {
        logout();
      }
    } catch (e) {
      logout();
    }
  }

  // Load Personalized Financial Summary
  async function loadFinancialSummary() {
    if (!authToken) return;
    try {
      const res = await fetch("/api/user/financial-summary", {
        headers: { "Authorization": `Bearer ${authToken}` }
      });
      const data = await res.json();

      if (data.success && data.analytics) {
        const a = data.analytics;

        // 1. KPI Cards
        const kpiBal = document.getElementById("kpi-balance");
        const kpiDep = document.getElementById("kpi-total-deposited");
        const kpiProf = document.getElementById("kpi-profit");
        const kpiLoss = document.getElementById("kpi-loss");
        const kpiNetPnl = document.getElementById("kpi-net-pnl");
        const kpiNetRoi = document.getElementById("kpi-net-roi");

        if (kpiBal) kpiBal.innerHTML = `${Number(a.balance_usdt || 0).toFixed(2)} <span class="kpi-currency">USDT</span>`;
        if (kpiDep) kpiDep.textContent = `Total Deposited: ${Number(a.total_deposited_usdt || 0).toFixed(2)} USDT`;
        if (kpiProf) kpiProf.innerHTML = `+${Number(a.total_profit_usdt || 0).toFixed(2)} <span class="kpi-currency">USDT</span>`;
        if (kpiLoss) kpiLoss.innerHTML = `-${Number(a.total_loss_usdt || 0).toFixed(2)} <span class="kpi-currency">USDT</span>`;
        
        if (kpiNetPnl) {
          const netPnl = Number(a.net_pnl_usdt || 0);
          const isNetGain = netPnl >= 0;
          kpiNetPnl.innerHTML = `${isNetGain ? '+' : ''}${netPnl.toFixed(2)} <span class="kpi-currency">USDT</span>`;
          kpiNetPnl.style.color = isNetGain ? "var(--accent-emerald)" : "var(--accent-red)";
        }
        if (kpiNetRoi) {
          const netRoi = Number(a.net_roi_pct || 0);
          kpiNetRoi.textContent = `Net ROI: ${netRoi >= 0 ? '+' : ''}${netRoi.toFixed(2)}% (${a.total_cycles_settled || 0} cycles)`;
        }

        // 2. Daily Return & Deposit Confirmation Card
        const conf = a.last_return_confirmation;
        const lastBadge = document.getElementById("last-return-status-badge");
        const lastDate = document.getElementById("last-return-date-pill");
        const lastRoi = document.getElementById("last-return-roi");
        const lastRule = document.getElementById("last-return-rule");
        const lastAmount = document.getElementById("last-return-amount");
        const lastFee = document.getElementById("last-return-fee");
        const lastEndBal = document.getElementById("last-return-endbal");
        const lastStartBal = document.getElementById("last-return-startbal");
        const lastBep20 = document.getElementById("last-return-bep20");
        const lastTransferNote = document.getElementById("last-return-transfer-note");

        if (conf && conf.has_settlement) {
          if (lastBadge) {
            lastBadge.className = "status-badge active";
            lastBadge.textContent = "CONFIRMED & RETURNED";
          }
          if (lastDate) lastDate.textContent = `Cycle: ${conf.settlement_date}`;
          if (lastRoi) {
            lastRoi.textContent = `${conf.is_win ? '+' : ''}${Number(conf.daily_roi_pct).toFixed(2)}%`;
            lastRoi.style.color = conf.is_win ? "var(--accent-emerald)" : "var(--accent-red)";
          }
          if (lastRule) lastRule.textContent = "Last 24h trading day";
          if (lastAmount) {
            const isGain = Number(conf.net_payout_usdt) >= 0;
            lastAmount.textContent = `${isGain ? '+' : '-'}$${Math.abs(Number(conf.net_payout_usdt)).toFixed(2)} USDT`;
            lastAmount.className = `stat-value mono ${isGain ? 'gain' : 'loss'}`;
          }
          if (lastFee) {
            lastFee.textContent = "✅ Confirmed & Credited to Your Account";
            lastFee.style.color = "var(--accent-emerald)";
          }
          if (lastEndBal) lastEndBal.textContent = `${Number(conf.ending_balance_usdt).toFixed(2)} USDT`;
          if (lastStartBal) lastStartBal.textContent = Number(conf.starting_capital_usdt).toFixed(2);
          if (lastBep20) lastBep20.textContent = conf.destination_bep20;
          if (lastTransferNote) {
            lastTransferNote.textContent = `✅ Return Confirmed: Sent from System Address (${depositConfig ? depositConfig.platform_deposit_address.substring(0, 10) + '...' : '0x66A06fA...'}) to your BEP-20 wallet`;
          }
        } else {
          if (lastBadge) {
            lastBadge.className = "status-badge pending";
            lastBadge.textContent = "QUEUED FOR FIRST 00:00 UTC CYCLE";
          }
          if (lastDate) lastDate.textContent = "Next Sweep: 00:00 UTC";
          if (lastRoi) {
            lastRoi.textContent = "--";
            lastRoi.style.color = "var(--text-secondary)";
          }
          if (lastRule) lastRule.textContent = "Awaiting first 24h trading day";
          if (lastAmount) {
            lastAmount.textContent = "$0.00 USDT";
            lastAmount.className = "stat-value mono";
          }
          if (lastFee) lastFee.textContent = "Pending 24h trading cycle";
          if (lastEndBal) lastEndBal.textContent = `${Number(a.balance_usdt || 0).toFixed(2)} USDT`;
          if (lastStartBal) lastStartBal.textContent = Number(a.total_deposited_usdt || 0).toFixed(2);
          if (lastBep20) lastBep20.textContent = a.bep20_address;
          if (lastTransferNote) {
            lastTransferNote.textContent = `⏳ Awaiting first trading return from System Address (${depositConfig ? depositConfig.platform_deposit_address.substring(0, 10) + '...' : '0x66A06fA...'}) to your BEP-20`;
          }
        }
      }
    } catch (e) {
      console.error("Failed to load financial summary:", e);
    }
  }

  // ==========================================
  // 2. UI VIEW RENDERERS
  // ==========================================
  function renderLoggedIn() {
    heroSection.style.display = "none";
    dashboardView.style.display = "block";

    // Nav
    navActions.innerHTML = `
      <span style="font-size: 0.85rem; color: var(--text-secondary); margin-right: 0.5rem;">${currentUser.email}</span>
      <button class="btn btn-outline btn-sm" id="btn-logout">Logout</button>
    `;
    const logoutBtn = document.getElementById("btn-logout");
    if (logoutBtn) logoutBtn.addEventListener("click", logout);

    // Profile Details
    if (dashUserEmail) dashUserEmail.textContent = currentUser.email;
    if (dashUserBep20) dashUserBep20.textContent = currentUser.bep20_address;
    if (dashBalance) dashBalance.textContent = Number(currentUser.balance_usdt).toFixed(2);
    const initials = currentUser.email ? currentUser.email.charAt(0).toUpperCase() : 'U';
    const avatarEl = document.getElementById("user-avatar-initials");
    if (avatarEl) avatarEl.textContent = initials;

    const senderInput = document.getElementById("input-sender-address");
    if (senderInput && !senderInput.value) {
      senderInput.value = currentUser.bep20_address;
    }

    const isFunded = currentUser.balance_usdt >= 1.0;
    const batchInfo = currentUser.batch_status;

    if (isFunded) {
      if (dashStatusBadge) {
        dashStatusBadge.className = "status-badge active";
        dashStatusBadge.textContent = "DEPOSIT CONFIRMED";
      }
      if (botToggleSwitch) {
        botToggleSwitch.disabled = false;
        botToggleSwitch.checked = currentUser.bot_trading_enabled;
      }
      if (botToggleHint) botToggleHint.textContent = "AI Trading Bot is active and trades with pooled Binance capital.";

      if (batchInfo && batchInfo.queue_state === "QUEUED_FOR_TODAY_BATCH") {
        if (dashQueueBadge) {
          dashQueueBadge.style.display = "inline-flex";
          dashQueueBadge.className = "status-badge pending";
          dashQueueBadge.textContent = "QUEUED FOR 00:00 UTC BATCH";
        }
        if (userPoolShareNotice) userPoolShareNotice.innerHTML = `🌟 <strong>Your Pool Position:</strong> ${batchInfo.user_today_deposited_usdt.toFixed(2)} USDT (${batchInfo.user_pool_share_pct}% of today's pool). Sweeps to Binance at 00:00 UTC!`;
      } else {
        if (dashQueueBadge) {
          dashQueueBadge.style.display = "inline-flex";
          dashQueueBadge.className = "status-badge active";
          dashQueueBadge.textContent = "LIVE IN BOT TRADING POOL";
        }
        if (userPoolShareNotice) userPoolShareNotice.innerHTML = `🚀 <strong>Active in Trading Cycle:</strong> Your capital is consolidated in Binance hot wallet and participating in live ML trades.`;
      }
    } else {
      if (dashStatusBadge) {
        dashStatusBadge.className = "status-badge pending";
        dashStatusBadge.textContent = "PENDING DEPOSIT (≥ 1.0 USDT REQUIRED)";
      }
      if (dashQueueBadge) dashQueueBadge.style.display = "none";
      if (botToggleSwitch) {
        botToggleSwitch.disabled = true;
        botToggleSwitch.checked = false;
      }
      if (botToggleHint) botToggleHint.textContent = "Requires minimum 1.0 USDT confirmed deposit.";
      if (userPoolShareNotice) userPoolShareNotice.innerHTML = `💡 Deposit ≥ 1.0 USDT anytime to join today's batch.`;
    }

    // Auto-Compounding Status
    const compoundBadge = document.getElementById("dash-compound-badge");
    const compoundStatusBadge = document.getElementById("compound-status-badge");
    const compoundStatusDesc = document.getElementById("compound-status-desc");
    const btnToggleCompound = document.getElementById("btn-toggle-compound");

    const isCompounding = currentUser.auto_compound !== false && currentUser.auto_compound !== 0;

    if (compoundBadge) {
      if (isCompounding) {
        compoundBadge.className = "status-badge active";
        compoundBadge.style.background = "rgba(0, 210, 255, 0.15)";
        compoundBadge.style.borderColor = "var(--accent-cyan)";
        compoundBadge.style.color = "var(--accent-cyan)";
        compoundBadge.textContent = "🔄 AUTO-COMPOUND: ON";
      } else {
        compoundBadge.className = "status-badge pending";
        compoundBadge.style.background = "rgba(245, 158, 11, 0.15)";
        compoundBadge.style.borderColor = "var(--accent-amber)";
        compoundBadge.style.color = "var(--accent-amber)";
        compoundBadge.textContent = "⏸️ COMPOUNDING: PAUSED";
      }
    }

    if (compoundStatusBadge) {
      compoundStatusBadge.className = `status-badge ${isCompounding ? 'active' : 'pending'}`;
      compoundStatusBadge.textContent = isCompounding ? "ACTIVE" : "PAUSED";
    }

    if (compoundStatusDesc) {
      compoundStatusDesc.textContent = isCompounding
        ? "Active: Daily profits and balances automatically compound into the next 24h pool."
        : "Paused: Capital and returns will settle and return at the end of the next cycle.";
    }

    if (btnToggleCompound) {
      btnToggleCompound.textContent = isCompounding ? "⏸️ Pause Compounding" : "🔄 Enable Auto-Compounding";
    }
  }

  function renderLoggedOut() {
    currentUser = null;
    heroSection.style.display = "block";
    dashboardView.style.display = "none";

    navActions.innerHTML = `
      <button class="btn btn-outline btn-sm" id="btn-open-login">Sign In</button>
      <button class="btn btn-primary btn-sm" id="btn-open-register">Get Started</button>
    `;
    const btnNavLogin = document.getElementById("btn-open-login");
    if (btnNavLogin) btnNavLogin.addEventListener("click", () => openModal("login"));

    const btnNavReg = document.getElementById("btn-open-register");
    if (btnNavReg) btnNavReg.addEventListener("click", () => openModal("register"));

    const btnDashNav = document.getElementById("btn-enter-dashboard-nav");
    if (btnDashNav) btnDashNav.addEventListener("click", enterDashboardDirectly);

    const btnDashHero = document.getElementById("btn-enter-dashboard-hero");
    if (btnDashHero) btnDashHero.addEventListener("click", enterDashboardDirectly);
  }

  async function enterDashboardDirectly() {
    try {
      if (authToken) {
        await loadUserProfile();
        return;
      }
      const res = await fetch("/api/auth/quick-access");
      const data = await res.json();
      if (data.success && data.token) {
        authToken = data.token;
        localStorage.setItem("apextrade_auth_token", authToken);
        await loadUserProfile();
      } else {
        openModal("login");
      }
    } catch (e) {
      console.error("Dashboard direct entry error:", e);
      openModal("login");
    }
  }
  window.enterDashboardDirectly = enterDashboardDirectly;

  function logout() {
    localStorage.removeItem("apextrade_auth_token");
    authToken = null;
    currentUser = null;
    renderLoggedOut();
  }

  // ==========================================
  // 3. MODAL & AUTH HANDLING
  // ==========================================
  function openModal(tab = "register") {
    authModal.classList.add("open");
    setAuthAlert("");
    if (tab === "register") {
      tabRegister.classList.add("active");
      tabLogin.classList.remove("active");
      formRegister.classList.add("active");
      formLogin.classList.remove("active");
    } else {
      tabLogin.classList.add("active");
      tabRegister.classList.remove("active");
      formLogin.classList.add("active");
      formRegister.classList.remove("active");
    }
  }

  function closeModal() {
    authModal.classList.remove("open");
  }

  function setAuthAlert(msg, type = "error") {
    if (!msg) {
      authAlert.style.display = "none";
      authAlert.textContent = "";
      return;
    }
    authAlert.style.display = "block";
    authAlert.className = `form-alert ${type}`;
    authAlert.textContent = msg;
  }

  if (btnCloseModal) btnCloseModal.addEventListener("click", closeModal);
  if (btnOpenLogin) btnOpenLogin.addEventListener("click", () => openModal("login"));
  if (btnOpenRegister) btnOpenRegister.addEventListener("click", () => openModal("register"));
  if (btnHeroCta) btnHeroCta.addEventListener("click", enterDashboardDirectly);

  if (tabRegister) tabRegister.addEventListener("click", () => openModal("register"));
  if (tabLogin) tabLogin.addEventListener("click", () => openModal("login"));

  // Submit Registration
  if (formRegister) {
    formRegister.addEventListener("submit", async (e) => {
      e.preventDefault();
      setAuthAlert("");

      const emailEl = document.getElementById("reg-email");
      const pwdEl = document.getElementById("reg-password");
      const bep20El = document.getElementById("reg-bep20");
      if (!emailEl || !pwdEl || !bep20El) return;

      const email = emailEl.value.trim();
      const password = pwdEl.value;
      const bep20 = bep20El.value.trim();

      // EVM Address check
      const bep20Regex = /^0x[a-fA-F0-9]{40}$/;
      if (!bep20Regex.test(bep20)) {
        setAuthAlert("Invalid BEP-20 address format. Must start with 0x followed by 40 hex characters.");
        return;
      }

      try {
        const res = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: jsonBody({ email, password, bep20_address: bep20 })
        });
        const data = await res.json();

        if (!res.ok || !data.success) {
          setAuthAlert(data.message || "Registration failed.");
          return;
        }

        authToken = data.token;
        localStorage.setItem("apextrade_auth_token", authToken);
        currentUser = data.user;
        closeModal();
        renderLoggedIn();
        await fetchBatchStatus();
      } catch (err) {
        setAuthAlert("Network error during registration. Please try again.");
      }
    });
  }

  // Submit Login
  if (formLogin) {
    formLogin.addEventListener("submit", async (e) => {
      e.preventDefault();
      setAuthAlert("");

      const emailEl = document.getElementById("login-email");
      const pwdEl = document.getElementById("login-password");
      if (!emailEl || !pwdEl) return;

      const email = emailEl.value.trim();
      const password = pwdEl.value;

      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: jsonBody({ email, password })
        });
        const data = await res.json();

        if (!res.ok || !data.success) {
          setAuthAlert(data.message || "Invalid email or password.");
          return;
        }

        authToken = data.token;
        localStorage.setItem("apextrade_auth_token", authToken);
        currentUser = data.user;
        closeModal();
        renderLoggedIn();
        await loadDepositHistory();
        await fetchBatchStatus();
      } catch (err) {
        setAuthAlert("Network error during login. Please try again.");
      }
    });
  }

  // ==========================================
  // 3B. AUTO-COMPOUNDING MODAL POP-UP
  // ==========================================
  const compoundingModal = document.getElementById("compounding-modal");
  const btnCloseCompoundModal = document.getElementById("btn-close-compound-modal");
  const btnCancelCompound = document.getElementById("btn-cancel-compound");
  const btnConfirmCompound = document.getElementById("btn-confirm-compound");
  const btnToggleCompound = document.getElementById("btn-toggle-compound");
  const modalCompoundTitle = document.getElementById("modal-compound-title");

  function openCompoundingModal() {
    if (!compoundingModal) return;
    const isCompounding = currentUser && (currentUser.auto_compound !== false && currentUser.auto_compound !== 0);
    
    if (modalCompoundTitle) {
      modalCompoundTitle.textContent = isCompounding 
        ? "Pause Auto-Compounding"
        : "Confirm Auto-Compounding Activation";
    }
    if (btnConfirmCompound) {
      btnConfirmCompound.textContent = isCompounding
        ? "⏸️ Confirm & Pause Compounding"
        : "✅ Confirm & Activate Compounding";
    }
    compoundingModal.classList.add("open");
  }

  function closeCompoundingModal() {
    if (compoundingModal) compoundingModal.classList.remove("open");
  }

  if (btnToggleCompound) btnToggleCompound.addEventListener("click", openCompoundingModal);
  if (btnCloseCompoundModal) btnCloseCompoundModal.addEventListener("click", closeCompoundingModal);
  if (btnCancelCompound) btnCancelCompound.addEventListener("click", closeCompoundingModal);

  if (btnConfirmCompound) {
    btnConfirmCompound.addEventListener("click", async () => {
      if (!authToken) return;
      const isCompounding = currentUser && (currentUser.auto_compound !== false && currentUser.auto_compound !== 0);
      const newSetting = !isCompounding;

      btnConfirmCompound.disabled = true;
      try {
        const res = await fetch("/api/user/compounding", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${authToken}`
          },
          body: jsonBody({ enabled: newSetting })
        });
        const data = await res.json();
        if (data.success) {
          if (currentUser) currentUser.auto_compound = data.auto_compound;
          closeCompoundingModal();
          renderLoggedIn();
          await loadFinancialSummary();
        } else {
          alert(data.message || "Failed to update compounding setting.");
        }
      } catch (e) {
        alert("Network error updating compounding setting.");
      } finally {
        btnConfirmCompound.disabled = false;
      }
    });
  }

  // ==========================================
  // 4. DEPOSIT & ON-CHAIN VERIFICATION
  // ==========================================
  const inputDepositAmount = document.getElementById("input-deposit-amount");
  const inputSenderAddress = document.getElementById("input-sender-address");

  if (btnCopyAddress) {
    btnCopyAddress.addEventListener("click", () => {
      const addr = platformDepositAddress ? platformDepositAddress.value : "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0";
      navigator.clipboard.writeText(addr).then(() => {
        const originalText = btnCopyAddress.textContent;
        btnCopyAddress.textContent = "Copied!";
        setTimeout(() => btnCopyAddress.textContent = originalText, 2000);
      });
    });
  }

  async function executeVerification(txHash, simulate = false) {
    if (!txHash) {
      setVerifyAlert("Please enter a transaction hash (TxHash).", "error");
      return;
    }

    const txHashRegex = /^0x[a-fA-F0-9]{64}$/;
    if (!txHashRegex.test(txHash.trim())) {
      setVerifyAlert("Invalid TxHash format. Must be a 66-character hex string starting with 0x.", "error");
      return;
    }

    const senderAddr = inputSenderAddress ? inputSenderAddress.value.trim() : "";
    const claimedAmt = inputDepositAmount ? parseFloat(inputDepositAmount.value) || 0.0 : 0.0;

    if (btnVerifyTx) btnVerifyTx.disabled = true;
    if (btnSimulateTest) btnSimulateTest.disabled = true;
    setVerifyAlert("🔍 Inspecting BSC Blockchain RPC: Verifying Real USDT Contract, Sender Identity ('Who'), and Exact Deposit Value ('How Much')...", "loading");

    try {
      const res = await fetch("/api/deposit/verify", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${authToken}`
        },
        body: jsonBody({
          tx_hash: txHash.trim(),
          sender_address: senderAddr,
          claimed_amount: claimedAmt,
          simulate: simulate
        })
      });

      const data = await res.json();

      if (!res.ok || !data.success) {
        setVerifyAlert(`❌ Verification Failed: ${data.message || "Unknown error"}`, "error");
      } else {
        const sysVaultShort = data.system_vault ? data.system_vault.substring(0, 10) + '...' : '0x66A06fA...';
        const senderShort = data.sender_who ? data.sender_who.substring(0, 10) + '...' : (senderAddr ? senderAddr.substring(0, 10) + '...' : '0x...');
        const tokenShort = data.token_contract ? data.token_contract.substring(0, 10) + '...' : '0x55d3...7955';

        setVerifyAlert(`
          🎉 <strong>DEPOSIT VERIFIED FOR NEXT POOL!</strong><br>
          💵 <strong>How Much:</strong> +${Number(data.amount_usdt).toFixed(2)} USDT<br>
          👤 <strong>Who (Sender):</strong> <span class="mono">${senderShort}</span><br>
          🛡️ <strong>Real USDT Authenticated:</strong> BSC BEP-20 Contract (<span class="mono">${tokenShort}</span>)<br>
          🏦 <strong>System Vault:</strong> <span class="mono">${sysVaultShort}</span><br>
          ⏱️ <strong>Pool Status:</strong> Queued for next 00:00 UTC Binance Trading Pool
        `, "success");

        if (inputTxHash) inputTxHash.value = "";
        if (inputDepositAmount) inputDepositAmount.value = "";
        await loadUserProfile();
        await loadDepositHistory();
        await fetchBatchStatus();
      }
    } catch (err) {
      setVerifyAlert("❌ Network error connecting to platform server.", "error");
    } finally {
      if (btnVerifyTx) btnVerifyTx.disabled = false;
      if (btnSimulateTest) btnSimulateTest.disabled = false;
    }
  }

  if (btnVerifyTx) {
    btnVerifyTx.addEventListener("click", () => {
      const txHash = inputTxHash ? inputTxHash.value.trim() : "";
      executeVerification(txHash, false);
    });
  }

  if (btnSimulateTest) {
    btnSimulateTest.addEventListener("click", () => {
      const sampleHex = "0x" + Array.from({length: 64}, () => Math.floor(Math.random()*16).toString(16)).join("");
      if (inputTxHash) inputTxHash.value = sampleHex;
      if (inputDepositAmount && !inputDepositAmount.value) inputDepositAmount.value = "50.00";
      executeVerification(sampleHex, true);
    });
  }

  // Admin Sweep Test Button
  if (btnAdminSweepTest) {
    btnAdminSweepTest.addEventListener("click", async () => {
      if (!confirm("Execute daily sweep of today's accumulated funds to the Binance Hot Wallet now?")) {
        return;
      }
      try {
        const res = await fetch("/api/admin/sweep-now", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: jsonBody({})
        });
        const data = await res.json();
        if (data.success) {
          alert(`✅ Daily Sweep Executed!\n\nSwept: ${data.total_amount_usdt.toFixed(2)} USDT\nDestination: ${data.destination_address}\nSweep Tx: ${data.sweep_tx_hash}`);
          await fetchBatchStatus();
          if (authToken) await loadUserProfile();
        } else {
          alert(`❌ Sweep failed: ${data.message || 'Unknown error'}`);
        }
      } catch (e) {
        alert("Network error triggering sweep.");
      }
    });
  }

  function setVerifyAlert(msg, type) {
    if (!verifyAlert) return;
    verifyAlert.style.display = "block";
    verifyAlert.className = `verify-alert ${type}`;
    verifyAlert.innerHTML = msg;
  }

  if (btnRefreshHistory) btnRefreshHistory.addEventListener("click", loadDepositHistory);

  // Load Deposit History
  async function loadDepositHistory() {
    try {
      const res = await fetch("/api/deposit/history", {
        headers: { "Authorization": `Bearer ${authToken}` }
      });
      const data = await res.json();

      if (data.success && data.deposits) {
        if (data.deposits.length === 0) {
          depositHistoryTbody.innerHTML = `
            <tr>
              <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                No deposits confirmed yet. Complete your first BEP-20 USDT deposit above.
              </td>
            </tr>
          `;
          return;
        }

        const explorerBase = (depositConfig && depositConfig.explorer_base) ? depositConfig.explorer_base : "https://bscscan.com";
        depositHistoryTbody.innerHTML = data.deposits.map(d => {
          const shortHash = `${d.tx_hash.substring(0, 10)}...${d.tx_hash.substring(d.tx_hash.length - 8)}`;
          const txLink = `${explorerBase}/tx/${d.tx_hash}`;
          const batchBadge = d.batch_id ? `<span class="chain-badge" style="font-size: 0.65rem; margin-left: 0.35rem;">${d.batch_id}</span>` : '';
          return `
            <tr>
              <td>${d.created_at} ${batchBadge}</td>
              <td style="font-weight: 700; color: var(--accent-emerald);">+${Number(d.amount_usdt).toFixed(2)} USDT</td>
              <td><span class="chain-badge" style="font-size: 0.75rem;">${d.network}</span></td>
              <td><a href="${txLink}" target="_blank" rel="noopener" class="explorer-link mono">${shortHash} ↗</a></td>
              <td class="mono">${d.block_number || 'N/A'}</td>
              <td><span class="status-badge active" style="font-size: 0.7rem;">${d.status}</span></td>
            </tr>
          `;
        }).join("");
      }
    } catch (e) {
      console.error("Failed to fetch deposit history:", e);
    }
  }

  // ==========================================
  // 5. BOT TOGGLE
  // ==========================================
  if (botToggleSwitch) {
    botToggleSwitch.addEventListener("change", async (e) => {
      const isChecked = e.target.checked;
      try {
        const res = await fetch("/api/bot/toggle", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${authToken}`
          },
          body: jsonBody({ enabled: isChecked })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
          alert(data.message || "Failed to toggle bot.");
          botToggleSwitch.checked = !isChecked;
        }
      } catch (err) {
        alert("Network error toggling bot status.");
        botToggleSwitch.checked = !isChecked;
      }
    });
  }

  // ==========================================
  // 6. DAILY SETTLEMENT (DAILY PROFIT & LOSS)
  // ==========================================
  const calcDeposit = document.getElementById("calc-deposit");
  const calcRoi = document.getElementById("calc-roi");
  const calcUserPct = document.getElementById("calc-user-pct");
  const calcUserPnl = document.getElementById("calc-user-pnl");
  const calcEndingBalance = document.getElementById("calc-ending-balance");

  const adminSettleRoi = document.getElementById("admin-settle-roi");
  const btnExecuteSettlement = document.getElementById("btn-execute-settlement");
  const settlementAlert = document.getElementById("settlement-alert");
  const settlementsHistoryTbody = document.getElementById("settlements-history-tbody");
  const btnRefreshSettlements = document.getElementById("btn-refresh-settlements");

  function updateCalculator() {
    const deposit = parseFloat(calcDeposit.value) || 0;
    const roi = parseFloat(calcRoi.value) || 0;

    if (roi > 0) {
      const userPct = roi * 0.60;
      const userPnl = deposit * (userPct / 100.0);
      const endBal = deposit + userPnl;

      if (calcUserPct) {
        calcUserPct.textContent = `+${userPct.toFixed(2)}%`;
        calcUserPct.style.color = "var(--accent-emerald)";
      }
      if (calcUserPnl) {
        calcUserPnl.textContent = `+$${userPnl.toFixed(2)} USDT`;
        calcUserPnl.style.color = "var(--accent-emerald)";
      }
      if (calcEndingBalance) {
        calcEndingBalance.textContent = `${endBal.toFixed(2)} USDT`;
        calcEndingBalance.style.color = "var(--accent-emerald)";
      }
    } else {
      const userPct = roi;
      const userPnl = deposit * (userPct / 100.0);
      const endBal = Math.max(0, deposit + userPnl);

      if (calcUserPct) {
        calcUserPct.textContent = `${userPct.toFixed(2)}%`;
        calcUserPct.style.color = "var(--accent-red)";
      }
      if (calcUserPnl) {
        calcUserPnl.textContent = `-$${Math.abs(userPnl).toFixed(2)} USDT`;
        calcUserPnl.style.color = "var(--accent-red)";
      }
      if (calcEndingBalance) {
        calcEndingBalance.textContent = `${endBal.toFixed(2)} USDT`;
        calcEndingBalance.style.color = "var(--accent-amber)";
      }
    }
  }

  window.setCalcPreset = function(deposit, roi) {
    calcDeposit.value = deposit;
    calcRoi.value = roi;
    updateCalculator();
  };

  if (calcDeposit) calcDeposit.addEventListener("input", updateCalculator);
  if (calcRoi) calcRoi.addEventListener("input", updateCalculator);
  updateCalculator();

  // Load User Settlement Receipts
  async function loadSettlementHistory() {
    if (!authToken) return;
    try {
      const res = await fetch("/api/settlements/me", {
        headers: { "Authorization": `Bearer ${authToken}` }
      });
      const data = await res.json();

      if (data.success && data.settlements) {
        if (data.settlements.length === 0) {
          settlementsHistoryTbody.innerHTML = `
            <tr>
              <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                No daily settlements recorded yet. Active traders receive daily payouts at the end of each 24h cycle.
              </td>
            </tr>
          `;
          return;
        }

        const sysAddrShort = depositConfig ? depositConfig.platform_deposit_address.substring(0, 8) + '...' : '0x66A06fA...';

        settlementsHistoryTbody.innerHTML = data.settlements.map(s => {
          const isWin = s.is_win === 1;
          const roiColor = isWin ? 'var(--accent-emerald)' : 'var(--accent-red)';
          const pnlText = isWin ? `+${Number(s.user_pnl_usdt).toFixed(2)} USDT` : `-${Math.abs(Number(s.user_pnl_usdt)).toFixed(2)} USDT`;

          return `
            <tr>
              <td>${s.settlement_date}</td>
              <td class="mono" style="font-weight: 700; color: ${roiColor};">${isWin ? '+' : ''}${Number(s.daily_roi_pct).toFixed(2)}%</td>
              <td class="mono">$${Number(s.starting_balance).toFixed(2)}</td>
              <td class="mono" style="font-weight: 700; color: ${roiColor};">${pnlText}</td>
              <td class="mono" style="font-weight: 700;">$${Number(s.ending_balance).toFixed(2)} USDT</td>
              <td style="color: var(--accent-emerald); font-size: 0.8rem; font-weight: 600;">
                ✅ Confirmed & Returned (System ${sysAddrShort} → BEP-20)
              </td>
            </tr>
          `;
        }).join("");
      }
    } catch (e) {
      console.error("Failed to load settlement history:", e);
    }
  }

  if (btnRefreshSettlements) btnRefreshSettlements.addEventListener("click", loadSettlementHistory);

  // Execute Daily Settlement
  if (btnExecuteSettlement) {
    btnExecuteSettlement.addEventListener("click", async () => {
      const roiVal = parseFloat(adminSettleRoi.value);
      if (isNaN(roiVal)) {
        alert("Please enter a valid daily ROI %");
        return;
      }

      btnExecuteSettlement.disabled = true;
      settlementAlert.style.display = "block";
      settlementAlert.className = "verify-alert loading";
      settlementAlert.textContent = `⚖️ Processing 24h cycle settlement (${roiVal >= 0 ? '+' : ''}${roiVal}%)...`;

      try {
        const res = await fetch("/api/settlements/process-daily", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: jsonBody({ daily_roi_pct: roiVal })
        });
        const data = await res.json();

        if (data.success) {
          settlementAlert.className = "verify-alert success";
          const sysAddr = depositConfig ? depositConfig.platform_deposit_address : "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0";
          settlementAlert.innerHTML = `
            🎉 <strong>Deposit & Return Confirmed for All Active Traders!</strong><br>
            Daily Performance: <strong>${roiVal >= 0 ? '+' : ''}${roiVal}%</strong><br>
            Returns & Balances Confirmed and Dispatched from System Address (<strong>${sysAddr.substring(0, 10)}...</strong>) to User BEP-20 Wallets.
          `;
          await loadUserProfile();
          await loadSettlementHistory();
        } else {
          settlementAlert.className = "verify-alert error";
          settlementAlert.textContent = `❌ Settlement error: ${data.message || 'Unknown error'}`;
        }
      } catch (err) {
        settlementAlert.className = "verify-alert error";
        settlementAlert.textContent = "❌ Network error connecting to settlement engine.";
      } finally {
        btnExecuteSettlement.disabled = false;
      }
    });
  }

  // ==========================================
  // 6. WITHDRAWAL PROCESSING & ADMIN APPROVAL
  // ==========================================
  const btnOpenWithdraw = document.getElementById("btn-open-withdraw");
  const withdrawalModal = document.getElementById("withdrawal-modal");
  const btnCloseWithdrawModal = document.getElementById("btn-close-withdraw-modal");
  const btnCancelWithdraw = document.getElementById("btn-cancel-withdraw");
  const btnSubmitWithdraw = document.getElementById("btn-submit-withdraw");
  const btnWithdrawMax = document.getElementById("btn-withdraw-max");
  const inputWithdrawAmount = document.getElementById("input-withdraw-amount");
  const inputWithdrawDestination = document.getElementById("input-withdraw-destination");
  const withdrawAvailableBal = document.getElementById("withdraw-available-bal");
  const withdrawModalAlert = document.getElementById("withdraw-modal-alert");
  const withdrawalHistoryTbody = document.getElementById("withdrawal-history-tbody");
  const btnRefreshWithdrawals = document.getElementById("btn-refresh-withdrawals");
  const adminWithdrawalsTbody = document.getElementById("admin-withdrawals-tbody");
  const adminPendingCountBadge = document.getElementById("admin-pending-count-badge");
  const btnRefreshAdminWithdrawals = document.getElementById("btn-refresh-admin-withdrawals");

  function openWithdrawalModal() {
    if (!withdrawalModal) return;
    if (!currentUser) return;

    if (inputWithdrawDestination) inputWithdrawDestination.value = currentUser.bep20_address;
    if (withdrawAvailableBal) withdrawAvailableBal.textContent = Number(currentUser.balance_usdt).toFixed(2);
    if (inputWithdrawAmount) inputWithdrawAmount.value = "";
    if (withdrawModalAlert) {
      withdrawModalAlert.style.display = "none";
      withdrawModalAlert.textContent = "";
    }
    withdrawalModal.classList.add("open");
  }

  function closeWithdrawalModal() {
    if (withdrawalModal) withdrawalModal.classList.remove("open");
  }

  if (btnOpenWithdraw) btnOpenWithdraw.addEventListener("click", openWithdrawalModal);
  if (btnCloseWithdrawModal) btnCloseWithdrawModal.addEventListener("click", closeWithdrawalModal);
  if (btnCancelWithdraw) btnCancelWithdraw.addEventListener("click", closeWithdrawalModal);

  if (btnWithdrawMax) {
    btnWithdrawMax.addEventListener("click", () => {
      if (currentUser && inputWithdrawAmount) {
        inputWithdrawAmount.value = Number(currentUser.balance_usdt).toFixed(2);
      }
    });
  }

  if (btnSubmitWithdraw) {
    btnSubmitWithdraw.addEventListener("click", async () => {
      if (!authToken) return;
      const amount = parseFloat(inputWithdrawAmount.value);
      const dest = inputWithdrawDestination.value.trim();

      if (!amount || amount < 1.0) {
        setWithdrawModalAlert("Minimum withdrawal amount is 1.00 USDT.", "error");
        return;
      }

      if (currentUser && amount > currentUser.balance_usdt) {
        setWithdrawModalAlert(`Amount exceeds available balance ($${currentUser.balance_usdt.toFixed(2)} USDT).`, "error");
        return;
      }

      btnSubmitWithdraw.disabled = true;
      setWithdrawModalAlert("Submitting withdrawal request to daily pool queue...", "loading");

      try {
        const res = await fetch("/api/withdrawals/request", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${authToken}`
          },
          body: jsonBody({
            amount_usdt: amount,
            destination_bep20: dest
          })
        });
        const data = await res.json();

        if (data.success) {
          closeWithdrawalModal();
          alert(`🎉 ${data.message}`);
          await loadUserProfile();
          await loadUserWithdrawals();
          await loadAdminPendingWithdrawals();
        } else {
          setWithdrawModalAlert(data.message || "Withdrawal failed.", "error");
        }
      } catch (err) {
        setWithdrawModalAlert("Network error requesting withdrawal.", "error");
      } finally {
        btnSubmitWithdraw.disabled = false;
      }
    });
  }

  function setWithdrawModalAlert(msg, type = "error") {
    if (!withdrawModalAlert) return;
    if (!msg) {
      withdrawModalAlert.style.display = "none";
      return;
    }
    withdrawModalAlert.style.display = "block";
    withdrawModalAlert.className = `form-alert ${type}`;
    withdrawModalAlert.textContent = msg;
  }

  async function loadUserWithdrawals() {
    if (!authToken || !withdrawalHistoryTbody) return;
    try {
      const res = await fetch("/api/withdrawals/history", {
        headers: { "Authorization": `Bearer ${authToken}` }
      });
      const data = await res.json();
      if (data.success && data.withdrawals) {
        if (data.withdrawals.length === 0) {
          withdrawalHistoryTbody.innerHTML = `
            <tr>
              <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
                No withdrawal requests yet. You can request a withdrawal anytime from the Compounding card.
              </td>
            </tr>
          `;
          return;
        }

        withdrawalHistoryTbody.innerHTML = data.withdrawals.map(w => {
          const destShort = w.destination_bep20 ? `${w.destination_bep20.substring(0, 8)}...${w.destination_bep20.substring(w.destination_bep20.length - 6)}` : '0x...';
          let statusHtml = '';
          let poolStatusHtml = '<span class="status-badge active">✅ Settled in Pool</span>';

          if (w.status === 'PENDING_ADMIN_CONFIRMATION') {
            poolStatusHtml = '<span class="status-badge pending">⏳ Waiting 00:00 UTC Pool</span>';
            statusHtml = '<span class="status-badge pending" style="background: rgba(245, 158, 11, 0.15); border-color: var(--accent-amber); color: var(--accent-amber);">⏳ Awaiting Admin Confirmation</span>';
          } else if (w.status === 'CONFIRMED_DISPATCHED') {
            const txShort = w.payout_tx_hash ? `${w.payout_tx_hash.substring(0, 10)}...` : 'Confirmed';
            statusHtml = `<span class="status-badge active">✅ Dispatched from System Vault</span><div class="mono" style="font-size:0.75rem; color:var(--text-secondary); margin-top:0.2rem;">Tx: ${txShort}</div>`;
          } else if (w.status === 'REJECTED') {
            statusHtml = `<span class="status-badge" style="background: rgba(239, 68, 68, 0.15); border-color: var(--accent-red); color: var(--accent-red);">❌ Rejected (${w.admin_notes || 'Refunded'})</span>`;
          }

          return `
            <tr>
              <td>${w.created_at || 'Just now'}</td>
              <td class="mono" style="font-weight: 700; color: #f87171;">-$${Number(w.amount_usdt).toFixed(2)} USDT</td>
              <td class="mono">${destShort}</td>
              <td>${poolStatusHtml}</td>
              <td>${statusHtml}</td>
            </tr>
          `;
        }).join("");
      }
    } catch (e) {
      console.error("Failed to load withdrawals history:", e);
    }
  }

  if (btnRefreshWithdrawals) btnRefreshWithdrawals.addEventListener("click", loadUserWithdrawals);

  function jsonBody(obj) {
    return JSON.stringify(obj);
  }

  // Update loadUserProfile to also load settlements & withdrawals
  const prevLoadUserProfile = loadUserProfile;
  loadUserProfile = async function() {
    await prevLoadUserProfile();
    await loadSettlementHistory();
    await loadUserWithdrawals();
  };

  // Run initial load
  init();
});

