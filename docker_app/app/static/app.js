function galleryApp() {
  return {
    currentView: "gallery",
    category: "all",
    navItems: [
      { key: "all", label: "全部项目", short: "全", copy: "所有图片与动态内容" },
      { key: "favorites", label: "收藏", short: "藏", copy: "只看已收藏动态" },
      { key: "livephoto", label: "Live Photo", short: "动", copy: "只看可播放动态" },
    ],
    meta: { counts: {}, years: {} },
    sidebarCounts: {},
    sidebarCountUpdatedAt: {},
    subscriptions: [],
    subscriptionPanel: ["up", "site"].includes(localStorage.getItem("subscription_panel"))
      ? localStorage.getItem("subscription_panel")
      : "up",
    selectedSubscriptionUids: [],
    sourceKind: ["all", "up", "site"].includes(localStorage.getItem("gallery_source_kind"))
      ? localStorage.getItem("gallery_source_kind")
      : "all",
    sourceKindOptions: [
      { key: "all", label: "所有项目" },
      { key: "up", label: "UP订阅" },
      { key: "site", label: "站点订阅" },
    ],
    gallery: { items: [], total: 0, page: 1, page_size: 24 },
    galleryLoading: false,
    galleryViewMode: localStorage.getItem("gallery_view_mode") || "folder",
    sortOrder: localStorage.getItem("gallery_time_sort_mode") === "random"
      ? "random"
      : (localStorage.getItem("gallery_sort_order") || "desc"),
    timeSortMode: localStorage.getItem("gallery_time_sort_mode") || "desc",
    galleryRenderKey: 0,
    galleryRequestId: 0,
    galleryColumnCount: (() => {
      const stored = Number(localStorage.getItem("gallery_column_count"));
      if (Number.isFinite(stored) && stored >= 1) {
        return stored;
      }
      const legacy = Number(localStorage.getItem("gallery_thumb_size") || 280);
      if (legacy >= 360) return 3;
      if (legacy >= 300) return 4;
      if (legacy >= 240) return 5;
      return 6;
    })(),
    detailColumnCount: (() => {
      const stored = Number(localStorage.getItem("detail_column_count"));
      if (Number.isFinite(stored) && stored >= 1) {
        return stored;
      }
      const legacy = Number(localStorage.getItem("detail_thumb_size") || 180);
      if (legacy >= 300) return 2;
      if (legacy >= 240) return 3;
      if (legacy >= 190) return 4;
      return 5;
    })(),
    detailLoading: false,
    detailRequestId: 0,
    detailClosing: false,
    detailCloseTimer: null,
    viewerClosing: false,
    viewerCloseTimer: null,
    headerCompact: false,
    headerScrollRaf: null,
    lastScrollTop: 0,
    reviewItems: [],
    logs: [],
    taskRuns: [],
    queuedTasks: [],
    trashItems: [],
    trashGroupExpanded: {},
    siteStats: {},
    siteStatus: {},
    siteSources: [],
    siteLogs: [],
    siteRules: { mode: "blacklist", keywords: [], allow_keywords: [], block_keywords: [], use_regex: false },
    siteRuleText: {
      allow_keywords: "",
      block_keywords: "",
      title_allow: "",
      title_block: "",
      tag_allow: "",
      tag_block: "",
    },
    sitePreviewItems: [],
    siteTestLoading: false,
    siteSuggestLoading: false,
    siteSuggestion: null,
    siteSourceForm: {},
    newSiteSourceExpanded: false,
    siteSourceExpanded: {},
    siteSourceDrafts: {},
    sitePreviewItemsById: {},
    siteTestLoadingById: {},
    siteSourceSaving: false,
    siteSourceSavingById: {},
    siteIconRefreshingById: {},
    siteRulesExpanded: false,
    siteLogsExpanded: false,
    siteLogsClearConfirm: false,
    siteValidateConfirmId: null,
    siteValidateConfirmStep: 0,
    siteClearDeleteConfirmId: null,
    siteClearDeleteConfirmStep: 0,
    settings: {},
    galleryIndexStatus: {},
    newSubscriptionUid: "",
    keywordText: "",
    pullStatus: {},
    qr: {},
    detail: { open: false, pairs: [], folder: null, videos: [] },
    detailCache: {},
    viewer: { open: false, pair: null, folder: null, showVideo: false },
    viewerSource: "detail",
    viewerSequence: [],
    viewerIndex: 0,
    viewerToken: 0,
    viewerImageReady: false,
    viewerSwapPending: false,
    viewerPendingDirection: "",
    viewerZoom: 1,
    viewerOffsetX: 0,
    viewerOffsetY: 0,
    viewerTransitionEnabled: true,
    viewerSwitchDirection: "",
    viewerSwitchTimer: null,
    viewerPlaybackTimer: null,
    viewerClickTimer: null,
    viewerGesture: {
      pointers: {},
      startX: 0,
      startY: 0,
      startOffsetX: 0,
      startOffsetY: 0,
      startZoom: 1,
      startDistance: 0,
      active: false,
      isPinch: false,
    },
    viewerWheelOffset: 0,
    viewerWheelTimer: null,
    timeFilterOpen: false,
    timeFilterDraft: { startIndex: 0, endIndex: 0 },
    timeFilterApplied: { startMonth: null, endMonth: null },
    timeFilterDrag: { active: false, handle: null },
    timeFilterApplyTimer: null,
    playbackModes: ["loop", "pingpong", "once", "pause"],
    playbackMode: localStorage.getItem("livephoto_playback_mode") || "once",
    loadingMore: false,
    hoverPreviewEnabled: localStorage.getItem("livephoto_hover_preview") !== "0",
    hoverPreviewTimer: null,
    hoverPreviewCard: null,
    sidebarCollapsed: localStorage.getItem("gallery_sidebar_collapsed") === "1",
    compactViewport: false,
    sidebarDrawerOpen: false,
    pendingTrashFolder: null,
    pendingRestoreTrashId: null,
    clearDataConfirmStep: 0,
    validateConfirmStep: 0,
    rebuildIndexConfirmStep: 0,
    resetIconsConfirmStep: 0,
    resetIconsRunning: false,
    fullReloadConfirmStep: 0,
    clearTaskLogsConfirmStep: 0,
    clearFilterLogsConfirmStep: 0,
    subscriptionReloadConfirmUid: null,
    subscriptionReloadConfirmStep: 0,
    subscriptionDeleteConfirmUid: null,
    subscriptionDeleteConfirmStep: 0,
    subscriptionIconRefreshingUid: null,
    subscriptionExpanded: {},
    iconLoadFailures: {},
    queuedCancelConfirmId: null,
    deletePairConfirmKey: null,
    deletePairConfirmStep: 0,
    pairDeletingKey: null,
    taskInspector: { open: false, title: "", subtitle: "", body: "" },
    sourcePreview: { open: false, url: "", title: "", subtitle: "" },
    taskInspectorLoading: false,
    toast: { open: false, tone: "info", title: "", message: "" },
    toastTimer: null,
    lastTaskId: null,
    lastRunning: false,
    viewerSyntheticTapUntil: 0,
    bodyLockTop: null,
    bodyLockPaddingRight: "",
    bodyLockStyles: null,
    lazyLoaded: {
      review: false,
      logs: false,
      tasks: false,
      trash: false,
      sites: false,
      settings: false,
    },

    async init() {
      this.updateViewportMode();
      this.resetSiteSourceForm();
      this.settings = { ...this.settings, auto_load_enabled: true };
      this.loadSidebarCounts().catch(() => {});
      this.refreshSidebarCounts().catch(() => {});
      await Promise.all([this.refreshStatus(), this.refreshMeta(), this.loadSubscriptions(), this.refreshGallery(true)]);
      window.setInterval(() => this.refreshStatus(), 5000);
      window.setInterval(() => {
        if (this.qr.image_data_url && this.currentView === "settings") {
          this.pollQrStatus();
        }
      }, 3000);
      window.addEventListener("scroll", () => this.scheduleScrollEffects(), { passive: true });
      window.addEventListener("keydown", (event) => this.handleKeydown(event));
      window.addEventListener("resize", () => this.updateViewportMode(), { passive: true });
      window.addEventListener("orientationchange", () => this.updateViewportMode(), { passive: true });
      document.documentElement.style.setProperty("--sidebar-state", this.sidebarCollapsed ? "collapsed" : "expanded");
      window.addEventListener("pointermove", (event) => this.timeFilterPointerMove(event));
      window.addEventListener("pointerup", () => this.finishTimeFilterDrag());
      window.addEventListener("pointercancel", () => this.finishTimeFilterDrag());
      this.updateHeaderState();
    },

    scheduleScrollEffects() {
      if (this.bodyLockTop !== null) {
        this.lastScrollTop = this.bodyLockTop;
        return;
      }
      this.lastScrollTop = window.scrollY || window.pageYOffset || 0;
      if (this.headerScrollRaf) {
        return;
      }
      this.headerScrollRaf = window.requestAnimationFrame(async () => {
        this.headerScrollRaf = null;
        this.updateHeaderState(this.lastScrollTop);
        await this.handleScroll();
      });
    },

    toggleSidebar() {
      if (this.compactViewport) {
        this.sidebarDrawerOpen = !this.sidebarDrawerOpen;
        return;
      }
      this.sidebarCollapsed = !this.sidebarCollapsed;
      localStorage.setItem("gallery_sidebar_collapsed", this.sidebarCollapsed ? "1" : "0");
      document.documentElement.style.setProperty("--sidebar-state", this.sidebarCollapsed ? "collapsed" : "expanded");
    },

    updateViewportMode() {
      const nextCompact = window.matchMedia("(max-width: 1100px), (max-aspect-ratio: 11/10)").matches;
      this.compactViewport = nextCompact;
      if (!nextCompact) {
        this.sidebarDrawerOpen = false;
      }
    },

    closeSidebarDrawer() {
      this.sidebarDrawerOpen = false;
    },

    scrollViewTop() {
      const workspace = document.querySelector(".workspace");
      if (workspace) {
        workspace.scrollTop = 0;
      }
      window.scrollTo({ top: 0, behavior: "auto" });
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    },

    async api(url, options = {}) {
      const response = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        const error = new Error(payload.detail || payload.message || "请求失败");
        this.notify("error", "请求失败", error.message);
        throw error;
      }
      return response.json();
    },

    setImmediateTaskFeedback(message, extras = {}) {
      this.pullStatus = {
        ...this.pullStatus,
        ...extras,
        message,
      };
    },

    setImmediateSiteTaskFeedback(message, extras = {}) {
      this.siteStatus = {
        ...this.siteStatus,
        ...extras,
        message,
      };
    },

    notify(tone, title, message) {
      if (this.toastTimer) {
        window.clearTimeout(this.toastTimer);
      }
      this.toast = { open: true, tone, title, message };
      this.toastTimer = window.setTimeout(() => {
        this.toast.open = false;
      }, 2600);
    },

    closeToast() {
      if (this.toastTimer) {
        window.clearTimeout(this.toastTimer);
      }
      this.toast.open = false;
    },

    handleKeydown(event) {
      if (event.key === "Escape") {
        this.handleEscape();
        return;
      }
      if (!this.viewer.open) {
        return;
      }
      if (event.key === "ArrowLeft") {
        this.showPreviousPair();
      }
      if (event.key === "ArrowRight") {
        this.showNextPair();
      }
    },

    handleEscape() {
      if (this.sourcePreview.open) {
        this.closeSourcePreview();
        return;
      }
      if (this.taskInspector.open) {
        this.closeTaskInspector();
        return;
      }
      if (this.viewer.open) {
        this.closeViewer();
        return;
      }
      if (this.detail.open) {
        this.closeDetail();
        return;
      }
      if (this.sidebarDrawerOpen) {
        this.closeSidebarDrawer();
        return;
      }
      this.closeToast();
    },

    currentSectionLabel() {
      if (this.currentView === "review") return "Review";
      if (this.currentView === "logs") return "Filter Log";
      if (this.currentView === "tasks") return "Task Queue";
      if (this.currentView === "trash") return "Trash";
      if (this.currentView === "settings") return "Settings";
      if (this.currentView === "subscriptions") return "Subscriptions";
      return "Library";
    },

    currentSectionTitle() {
      if (this.currentView === "review") return "待审核动态";
      if (this.currentView === "logs") return "过滤日志";
      if (this.currentView === "tasks") return "任务队列";
      if (this.currentView === "trash") return "内容垃圾桶";
      if (this.currentView === "settings") return "拉取与设置";
      if (this.currentView === "subscriptions") return "订阅管理";
      return this.activeCategory().label;
    },

    currentSectionHeadline() {
      if (this.currentView === "review") return "把推广动态拦在相簿之前";
      if (this.currentView === "logs") return "知道每一条动态为什么被筛出去";
      if (this.currentView === "settings") return "同步、账号权限与过滤策略";
      if (this.currentView === "subscriptions") return "统一管理 UP 主与站点订阅";
      return `${this.activeCategory().label}，按更像系统相册的方式浏览`;
    },

    activeCategory() {
      return this.navItems.find((item) => item.key === this.category) || this.navItems[0];
    },

    compactStats() {
      const counts = this.meta.counts || {};
      return [
        {
          label: "全部",
          value: counts.all || 0,
        },
        {
          label: "动态",
          value: counts.livephoto || 0,
        },
        {
          label: "收藏",
          value: counts.favorites || 0,
        },
        {
          label: "待审核",
          value: this.reviewItems.length || 0,
        },
      ];
    },

    sidebarCount(key) {
      if (key in (this.sidebarCounts || {})) {
        return this.sidebarCounts[key] || 0;
      }
      return this.meta.counts?.[key] || 0;
    },

    applySidebarCounts(payload) {
      const counts = payload?.counts || {};
      this.sidebarCounts = { ...this.sidebarCounts, ...counts };
      this.sidebarCountUpdatedAt = { ...this.sidebarCountUpdatedAt, ...(payload?.updated_at || {}) };
      this.meta = {
        ...this.meta,
        counts: {
          ...(this.meta.counts || {}),
          all: counts.all ?? this.meta.counts?.all ?? 0,
          favorites: counts.favorites ?? this.meta.counts?.favorites ?? 0,
          livephoto: counts.livephoto ?? this.meta.counts?.livephoto ?? 0,
        },
      };
      if (counts.sites !== undefined) {
        this.siteStats = { ...this.siteStats, source_count: counts.sites };
      }
    },

    async loadSidebarCounts() {
      const payload = await this.api("/api/sidebar-counts");
      this.applySidebarCounts(payload);
    },

    async refreshSidebarCounts(keys = null) {
      const payload = await this.api("/api/sidebar-counts/refresh", {
        method: "POST",
        body: JSON.stringify({ keys }),
      });
      this.applySidebarCounts(payload);
    },

    updateHeaderState(scrollTop = window.scrollY || window.pageYOffset || 0) {
      const compactEnter = 112;
      const compactExit = 18;
      if (this.headerCompact) {
        this.headerCompact = scrollTop > compactExit;
        return;
      }
      this.headerCompact = scrollTop > compactEnter;
    },

    resolveGalleryColumns() {
      const target = Math.max(1, Number(this.galleryColumnCount) || 1);
      const width = this.$refs.galleryStage?.clientWidth || window.innerWidth || 1280;
      const minItemWidth = this.galleryViewMode === "pair" ? 150 : 220;
      const gap = 18;
      const fit = Math.max(1, Math.floor((width + gap) / (minItemWidth + gap)));
      return Math.min(target, fit);
    },

    galleryMasonryStyle() {
      return `--gallery-columns: ${this.resolveGalleryColumns()};`;
    },

    resolveDetailColumns() {
      const target = Math.max(1, Number(this.detailColumnCount) || 1);
      const width = this.$refs.detailGrid?.clientWidth || this.$refs.detailShell?.clientWidth || window.innerWidth || 1280;
      const minItemWidth = 132;
      const gap = 16;
      const fit = Math.max(1, Math.floor((width + gap) / (minItemWidth + gap)));
      return Math.min(target, fit);
    },

    detailGridStyle() {
      return `--detail-columns: ${this.resolveDetailColumns()};`;
    },

    assetVisualStyle(item) {
      return `aspect-ratio: ${item.display_ratio || "1 / 1"}`;
    },

    galleryDensityCaption() {
      const count = this.resolveGalleryColumns();
      return this.galleryViewMode === "pair"
        ? `每行约显示 ${count} 组图片，系统会按可用宽度自适应排布`
        : `每行约显示 ${count} 个动态，系统会按可用宽度自适应排布`;
    },

    detailDensityCaption() {
      return `每行约显示 ${this.resolveDetailColumns()} 组缩略图，系统会按可用宽度自适应排布`;
    },

    setGalleryColumnCount(value) {
      this.galleryColumnCount = Number(value);
      localStorage.setItem("gallery_column_count", String(this.galleryColumnCount));
    },

    setDetailColumnCount(value) {
      this.detailColumnCount = Number(value);
      localStorage.setItem("detail_column_count", String(this.detailColumnCount));
    },

    setTimeSortMode(mode) {
      if (!["desc", "asc", "random"].includes(mode)) {
        return;
      }
      this.timeSortMode = mode;
      localStorage.setItem("gallery_time_sort_mode", mode);
      const resolvedOrder = mode === "random" ? "random" : mode;
      if (this.sortOrder !== resolvedOrder) {
        this.sortOrder = resolvedOrder;
        localStorage.setItem("gallery_sort_order", resolvedOrder);
      }
      this.closeViewer();
      this.closeDetail();
      window.scrollTo({ top: 0, behavior: "smooth" });
      this.refreshGallery(true);
    },

    async refreshMeta() {
      const previousCounts = this.meta.counts || {};
      const payload = await this.api("/api/gallery/meta");
      this.meta = {
        ...payload,
        counts: { ...previousCounts, ...(payload.counts || {}) },
      };
      this.sidebarCounts = { ...this.sidebarCounts, ...(payload.counts || {}) };
      if (!this.selectedSubscriptionUids.length) {
        this.subscriptions = (this.subscriptions || []).map((item) => {
          const metaItem = (this.meta.subscriptions || []).find((entry) => entry.uid === item.uid);
          return metaItem ? { ...item, folder_count: metaItem.count } : item;
        });
      }
    },

    async loadSubscriptions() {
      const payload = await this.api("/api/subscriptions");
      const previousExpanded = { ...(this.subscriptionExpanded || {}) };
      this.subscriptions = (payload.items || []).map((item) => this.normalizeSubscriptionItem(item));
      this.sidebarCounts = { ...this.sidebarCounts, subscriptions: this.subscriptions.length };
      this.subscriptionExpanded = Object.fromEntries(
        this.subscriptions.map((item) => [String(item.uid), !!previousExpanded[String(item.uid)]]),
      );
    },

    normalizeSubscriptionItem(item) {
      return {
        ...item,
        is_site: !!item.is_site || String(item.uid || "").startsWith("site:"),
        avatar_url: item.avatar_url || "",
        icon_url: item.icon_url || item.avatar_url || "",
        pull_images: !!item.pull_images,
        pull_livephoto: !!item.pull_livephoto,
        include_forwarded: !!item.include_forwarded,
      };
    },

    upSubscriptions() {
      return (this.subscriptions || []).filter((item) => !item.is_site && !String(item.uid || "").startsWith("site:"));
    },

    siteSubscriptions() {
      return (this.subscriptions || []).filter((item) => item.is_site || String(item.uid || "").startsWith("site:"));
    },

    setSubscriptionPanel(panel) {
      if (!["up", "site"].includes(panel) || this.subscriptionPanel === panel) {
        return;
      }
      this.subscriptionPanel = panel;
      localStorage.setItem("subscription_panel", panel);
      this.scrollViewTop();
      if (panel === "site") {
        this.refreshSites();
        this.refreshSidebarCounts(["sites", "subscriptions"]).catch(() => {});
      } else {
        this.loadSubscriptions();
        this.refreshSidebarCounts(["subscriptions"]).catch(() => {});
      }
    },

    subscriptionPanelIndicatorStyle() {
      return `transform: translateX(${this.subscriptionPanel === "site" ? "100%" : "0"});`;
    },

    isSitePanelActive() {
      return this.currentView === "subscriptions" && this.subscriptionPanel === "site";
    },

    subscriptionIconUrl(item) {
      const key = String(item?.uid || "");
      if (!key || this.iconLoadFailures[key]) {
        return "";
      }
      return this.versionedIconUrl(item?.icon_url || item?.avatar_url || item?.site_icon_url || "", item?.updated_at);
    },

    handleSubscriptionIconError(item) {
      const key = String(item?.uid || "");
      if (!key) {
        return;
      }
      this.iconLoadFailures = { ...this.iconLoadFailures, [key]: true };
    },

    siteSourceIconUrl(source) {
      const key = `site:${source?.id || ""}`;
      if (!source?.icon_url || this.iconLoadFailures[key]) {
        return "";
      }
      return this.versionedIconUrl(source.icon_url, source.updated_at);
    },

    versionedIconUrl(url, version) {
      const value = String(url || "").trim();
      if (!value || !value.startsWith("/storage/") || !version) {
        return value;
      }
      const separator = value.includes("?") ? "&" : "?";
      return `${value}${separator}v=${encodeURIComponent(String(version))}`;
    },

    isSubscriptionExpanded(uid) {
      return !!this.subscriptionExpanded[String(uid)];
    },

    toggleSubscriptionExpanded(uid) {
      const key = String(uid);
      this.subscriptionExpanded = {
        ...this.subscriptionExpanded,
        [key]: !this.subscriptionExpanded[key],
      };
    },

    subscriptionThresholdSummary(item) {
      const value = Number(item.image_min_count);
      if (value === -1) {
        return "图片关闭";
      }
      return `阈值 ${Number.isFinite(value) ? value : 6}`;
    },

    subscriptionLivePhotoSummary(item) {
      return item.pull_livephoto ? "Live Photo 开" : "Live Photo 关";
    },

    subscriptionBadgeText(item) {
      if (String(item?.uid || "").startsWith("site:")) {
        return "站";
      }
      const source = String(item?.uname || item?.uid || "").trim();
      const chinese = source.match(/[\u4e00-\u9fff]/g);
      if (chinese && chinese.length) {
        return chinese[0];
      }
      const letters = source.replace(/[^a-zA-Z]/g, "").slice(0, 2);
      if (letters) {
        return letters.toUpperCase();
      }
      return source.slice(0, 1).toUpperCase() || "?";
    },

    async refreshGallery(reset = false) {
      const requestId = ++this.galleryRequestId;
      this.galleryLoading = reset;
      const existingLength = reset ? 0 : this.gallery.items.length;
      if (reset) {
        const pageSize = this.gallery.page_size || 24;
        this.gallery = { ...this.gallery, page: 1, page_size: pageSize };
      }
      const params = new URLSearchParams({
        category: this.category,
        view_mode: this.galleryViewMode,
        sort_order: this.sortOrder,
        page: String(this.gallery.page),
        page_size: String(this.gallery.page_size || 24),
      });
      if (this.timeFilterApplied.startMonth) {
        params.set("start_month", this.timeFilterApplied.startMonth);
      }
      if (this.timeFilterApplied.endMonth) {
        params.set("end_month", this.timeFilterApplied.endMonth);
      }
      if (this.selectedSubscriptionUids.length) {
        params.set("subscription_uids", this.selectedSubscriptionUids.join(","));
      } else if (this.sourceKind !== "all") {
        params.set("source_kind", this.sourceKind);
      }
      try {
        const payload = await this.api(`/api/gallery/items?${params.toString()}`);
        if (requestId !== this.galleryRequestId) {
          return;
        }
        if (reset) {
          this.gallery = payload;
        } else {
          const merged = this.mergeGalleryItems(this.gallery.items, payload.items || []);
          const appendedUnique = Math.max(0, merged.length - existingLength);
          this.gallery = {
            ...payload,
            items: merged,
            total: merged.length >= payload.total || (payload.items || []).length === 0 || appendedUnique === 0 ? merged.length : payload.total,
          };
        }
        if (this.autoLoadEnabled()) {
          this.$nextTick(() => this.handleScroll());
        }
      } finally {
        if (requestId === this.galleryRequestId) {
          this.galleryLoading = false;
        }
      }
    },

    mergeGalleryItems(existingItems, incomingItems) {
      const output = [];
      const seen = new Set();
      [...existingItems, ...incomingItems].forEach((item) => {
        const key = item.item_key || item.folder_name;
        if (!key || seen.has(key)) {
          return;
        }
        seen.add(key);
        output.push(item);
      });
      return output;
    },

    async loadMore() {
      if (this.loadingMore || this.gallery.items.length >= this.gallery.total) {
        return;
      }
      this.loadingMore = true;
      this.gallery.page += 1;
      try {
        await this.refreshGallery(false);
      } finally {
        this.loadingMore = false;
      }
    },

    openGallery(category) {
      this.currentView = "gallery";
      this.category = category;
      this.selectedSubscriptionUids = [];
      this.queuedCancelConfirmId = null;
      this.closeSidebarDrawer();
      this.closeViewer();
      this.closeDetail();
      this.timeFilterOpen = false;
      this.scrollViewTop();
      this.refreshGallery(true);
      this.refreshSidebarCounts([category]).catch(() => {});
    },

    openSubscriptions(panel = null) {
      this.currentView = "subscriptions";
      if (["up", "site"].includes(panel)) {
        this.subscriptionPanel = panel;
        localStorage.setItem("subscription_panel", panel);
      }
      this.closeSidebarDrawer();
      this.scrollViewTop();
      if (this.subscriptionPanel === "site") {
        this.refreshSites();
        this.refreshSidebarCounts(["subscriptions", "sites"]).catch(() => {});
      } else {
        this.loadSubscriptions();
        this.refreshSidebarCounts(["subscriptions"]).catch(() => {});
      }
    },

    openSites() {
      this.openSubscriptions("site");
    },

    openSettings() {
      this.currentView = "settings";
      this.closeSidebarDrawer();
      this.scrollViewTop();
      this.loadSettings();
    },

    openReview() {
      this.currentView = "review";
      this.closeSidebarDrawer();
      this.scrollViewTop();
      this.refreshReview();
      this.refreshSidebarCounts(["review"]).catch(() => {});
    },

    openLogs() {
      this.currentView = "logs";
      this.closeSidebarDrawer();
      this.scrollViewTop();
      this.refreshLogs();
      this.refreshSidebarCounts(["logs"]).catch(() => {});
    },

    selectSubscription(uid) {
      this.currentView = "gallery";
      this.category = "all";
      this.selectedSubscriptionUids = [String(uid)];
      this.queuedCancelConfirmId = null;
      this.closeSidebarDrawer();
      this.closeViewer();
      this.closeDetail();
      this.timeFilterOpen = false;
      this.scrollViewTop();
      this.refreshGallery(true);
      this.refreshSidebarCounts(["all"]).catch(() => {});
    },

    toggleSubscriptionFilter(uid) {
      const normalized = String(uid);
      if (this.selectedSubscriptionUids.includes(normalized)) {
        this.selectedSubscriptionUids = this.selectedSubscriptionUids.filter((item) => item !== normalized);
      } else {
        this.selectedSubscriptionUids = [...this.selectedSubscriptionUids, normalized];
      }
      this.queuedCancelConfirmId = null;
      this.refreshGallery(true);
    },

    subscriptionFilterActive(uid) {
      return this.selectedSubscriptionUids.includes(String(uid));
    },

    setSourceKind(kind) {
      if (!["all", "up", "site"].includes(kind) || this.sourceKind === kind) {
        return;
      }
      this.sourceKind = kind;
      localStorage.setItem("gallery_source_kind", kind);
      this.closeViewer();
      this.closeDetail();
      this.scrollViewTop();
      this.refreshGallery(true);
    },

    setGalleryViewMode(mode) {
      if (mode !== "folder" && mode !== "pair") {
        return;
      }
      this.galleryViewMode = mode;
      localStorage.setItem("gallery_view_mode", mode);
      this.closeViewer();
      this.closeDetail();
      this.timeFilterOpen = false;
      window.scrollTo({ top: 0, behavior: "smooth" });
      this.refreshGallery(true);
    },

    setSortOrder(order) {
      if (order !== "asc" && order !== "desc") {
        return;
      }
      this.sortOrder = order;
      this.timeSortMode = order;
      localStorage.setItem("gallery_time_sort_mode", order);
      localStorage.setItem("gallery_sort_order", order);
      this.closeViewer();
      this.closeDetail();
      window.scrollTo({ top: 0, behavior: "smooth" });
      this.refreshGallery(true);
    },

    setHoverPreviewEnabled(enabled) {
      this.hoverPreviewEnabled = !!enabled;
      localStorage.setItem("livephoto_hover_preview", this.hoverPreviewEnabled ? "1" : "0");
      if (!this.hoverPreviewEnabled) {
        document.querySelectorAll(".hover-preview-video").forEach((video) => {
          const card = video.closest(".asset-card, .detail-card");
          if (card) {
            this.stopHoverPreviewByCard(card);
          }
        });
      }
    },

    isNearBottom() {
      return window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 96;
    },

    hasMoreItems() {
      return this.gallery.items.length < this.gallery.total;
    },

    galleryReadyForLoad() {
      return (
        this.currentView === "gallery" &&
        !this.detail.open &&
        !this.detailClosing &&
        !this.viewer.open &&
        !this.viewerClosing &&
        !this.taskInspector.open &&
        this.bodyLockTop === null &&
        this.hasMoreItems()
      );
    },

    randomModeActive() {
      return this.timeSortMode === "random";
    },

    autoLoadEnabled() {
      return !!this.settings.auto_load_enabled && !this.randomModeActive();
    },

    showManualLoadMore() {
      return this.galleryReadyForLoad() && !this.autoLoadEnabled() && !this.randomModeActive();
    },

    showRandomReloadButton() {
      return this.currentView === "gallery" && this.gallery.items.length > 0 && this.randomModeActive();
    },

    async handleScroll() {
      if (!this.autoLoadEnabled() || !this.galleryReadyForLoad() || !this.isNearBottom()) {
        return;
      }
      await this.loadMore();
    },

    galleryLoadFinished() {
      if (this.randomModeActive()) {
        return false;
      }
      return this.gallery.items.length > 0 && this.gallery.items.length >= this.gallery.total;
    },

    async rerollRandomGallery() {
      if (!this.randomModeActive() || this.galleryLoading || this.loadingMore) {
        return;
      }
      this.notify("info", "正在重新随机抽取", "前端会先更新，后台正在刷新当前筛选结果。");
      this.scrollViewTop();
      await this.refreshGallery(true);
    },

    async openFolder(folderName) {
      if (this.detailCloseTimer) {
        window.clearTimeout(this.detailCloseTimer);
        this.detailCloseTimer = null;
      }
      this.cancelDeleteViewerPair();
      this.pauseCurrentViewerMedia(true);
      this.detailClosing = false;
      this.detailRequestId += 1;
      const requestId = this.detailRequestId;
      const previewFolder = (this.gallery.items || []).find((item) => item.folder_name === folderName);
      const cached = this.cachedDetail(folderName);
      if (cached) {
        this.detailLoading = false;
        this.detail = {
          ...cached,
          open: true,
          folder: previewFolder ? { ...cached.folder, ...previewFolder } : cached.folder,
        };
        this.syncBodyLock();
        return;
      }
      this.detailLoading = true;
      const previewPairs = this.detailPreviewPairs(folderName, previewFolder);
      this.detail = {
        open: true,
        pairs: this.detail.folder?.folder_name === folderName ? this.detail.pairs : previewPairs,
        folder: previewFolder || this.detail.folder || { folder_name: folderName, title: folderName },
        videos: this.detail.folder?.folder_name === folderName ? (this.detail.videos || []) : [],
      };
      this.syncBodyLock();
      try {
        const payload = await this.api(`/api/gallery/folders/${encodeURIComponent(folderName)}`);
        if (requestId !== this.detailRequestId) {
          return;
        }
        this.detailLoading = false;
        this.detail = {
          open: true,
          pairs: this.normalizeDetailPairs(payload.pairs || []),
          folder: payload.folder,
          videos: payload.videos || [],
        };
        this.cacheDetailPayload(folderName, this.detail);
        this.scheduleDetailThumbnailPromotion(folderName, requestId);
        this.syncBodyLock();
      } catch (error) {
        if (requestId !== this.detailRequestId) {
          return;
        }
        this.detailLoading = false;
        this.closeDetail(true);
      }
    },

    detailPreviewPairs(folderName, previewFolder) {
      if (this.galleryViewMode === "pair") {
        return (this.gallery.items || [])
          .filter((item) => item.folder_name === folderName)
          .map((item) => ({
            pair_index: Number(item.pair_index) || 0,
            image: item.image || {
              small_thumb_url: item.small_thumb_url,
              thumb_url: item.thumb_url,
              url: item.preview_url,
              width: item.width,
              height: item.height,
            },
            livephoto: item.livephoto || null,
            preview_url: item.small_thumb_url || item.thumb_url || item.preview_url,
            preview_kind: item.preview_kind || (item.has_livephoto ? "paired" : "image"),
            complete: !!(item.has_images && item.has_livephoto),
            display_ratio: item.display_ratio || "1 / 1",
            promote_preview: false,
          }));
      }
      return (previewFolder?.preview_tiles || []).map((tile, index) => ({
        pair_index: Number(tile.pair_index) || index + 1,
        image: {
          ...tile,
          url: tile.url || tile.thumb_url || tile.small_thumb_url,
        },
        livephoto: null,
        preview_url: tile.small_thumb_url || tile.thumb_url || tile.cover_url || tile.url,
        preview_kind: "image",
        complete: false,
        display_ratio: this.assetRatio(tile),
        promote_preview: false,
      }));
    },

    normalizeDetailPairs(pairs) {
      return (pairs || []).map((pair) => ({ ...pair, promote_preview: false }));
    },

    assetRatio(asset) {
      const width = Number(asset?.width || 0);
      const height = Number(asset?.height || 0);
      if (width > 0 && height > 0) {
        return `${width} / ${height}`;
      }
      return "1 / 1";
    },

    detailPairPreviewUrl(pair) {
      const image = pair?.image || {};
      const livephoto = pair?.livephoto || {};
      if (pair?.promote_preview) {
        return image.thumb_url || livephoto.thumb_url || image.small_thumb_url || livephoto.small_thumb_url || pair.preview_url || image.url || livephoto.cover_url || livephoto.url;
      }
      return image.small_thumb_url || livephoto.small_thumb_url || pair?.preview_url || image.thumb_url || livephoto.thumb_url || image.url || livephoto.cover_url || livephoto.url;
    },

    scheduleDetailThumbnailPromotion(folderName, requestId) {
      const promoteNext = (index = 0) => {
        if (requestId !== this.detailRequestId || this.detail.folder?.folder_name !== folderName) {
          return;
        }
        const pairs = this.detail.pairs || [];
        if (index >= pairs.length) {
          this.cacheDetailPayload(folderName, this.detail);
          return;
        }
        const end = Math.min(index + 6, pairs.length);
        this.detail = {
          ...this.detail,
          pairs: pairs.map((pair, pairIndex) => (
            pairIndex >= index && pairIndex < end ? { ...pair, promote_preview: true } : pair
          )),
        };
        const schedule = window.requestIdleCallback || ((callback) => window.setTimeout(callback, 80));
        schedule(() => promoteNext(end));
      };
      window.setTimeout(() => promoteNext(0), 80);
    },

    openPair(pairIndex) {
      const sequence = this.buildDetailViewerSequence();
      const index = sequence.findIndex((item) => this.viewerEntryKey(item) === `${this.detail.folder?.folder_name}::${pairIndex}`);
      if (index < 0) return;
      this.viewerSource = "detail";
      this.viewerSequence = sequence;
      this.viewerIndex = index;
      this.openViewerEntry(sequence[index]);
    },

    openViewerEntry(entry, preservePlayback = false, startImmediately = true, switchDirection = "") {
      if (!entry?.pair) {
        return;
      }
      if (this.viewerCloseTimer) {
        window.clearTimeout(this.viewerCloseTimer);
        this.viewerCloseTimer = null;
      }
      this.viewerClosing = false;
      this.pauseCurrentViewerMedia(true);
      const pair = entry.pair;
      this.viewerToken += 1;
      const shouldShowVideo = !!pair.livephoto && !pair.image;
      this.viewerImageReady = !pair.image;
      this.viewerSwapPending = !!switchDirection;
      this.viewerPendingDirection = switchDirection || "";
      this.viewer = { open: true, pair, folder: entry.folder, showVideo: shouldShowVideo };
      this.cancelDeleteViewerPair();
      if (!preservePlayback) {
        this.playbackMode = "once";
        localStorage.setItem("livephoto_playback_mode", this.playbackMode);
      }
      this.resetViewerTransform();
      this.syncBodyLock();
      this.$nextTick(() => {
        if (shouldShowVideo) {
          document.querySelectorAll(".viewer-video").forEach((video) => this.applyPlaybackMode(video));
        } else if (pair.livephoto && pair.image && !this.viewerSwapPending && startImmediately) {
          this.scheduleViewerPlaybackStart();
        }
      });
    },

    scheduleViewerPlaybackStart() {
      if (!this.viewer.pair?.livephoto || !this.viewer.pair?.image || this.playbackMode === "pause") {
        return;
      }
      if (this.viewerPlaybackTimer) {
        window.clearTimeout(this.viewerPlaybackTimer);
      }
      const folderName = this.viewer.folder?.folder_name;
      const pairIndex = this.viewer.pair?.pair_index;
      const viewerToken = this.viewerToken;
      this.viewerPlaybackTimer = window.setTimeout(() => {
        this.viewerPlaybackTimer = null;
        if (!this.viewer.open) {
          return;
        }
        if (this.viewerToken !== viewerToken || this.viewer.folder?.folder_name !== folderName || this.viewer.pair?.pair_index !== pairIndex) {
          return;
        }
        const video = document.querySelector(".viewer-video");
        if (!video || video.dataset.viewerToken !== String(viewerToken)) {
          return;
        }
        this.viewer.showVideo = true;
        this.$nextTick(() => this.applyPlaybackMode(video, true));
      }, 160);
    },

    openGalleryPair(item) {
      const sequence = this.buildGalleryViewerSequence();
      const itemKey = item.item_key || `${item.folder_name}::${item.pair_index}`;
      const index = sequence.findIndex((entry) => this.viewerEntryKey(entry) === itemKey);
      this.viewerSource = "gallery";
      if (index >= 0) {
        this.viewerSequence = sequence;
        this.viewerIndex = index;
        this.openViewerEntry(sequence[index]);
        return;
      }
      this.viewerSequence = [
        {
          pair: {
            item_key: itemKey,
            pair_index: item.pair_index,
            image: item.image,
            livephoto: item.livephoto,
            preview_url: item.preview_url,
            preview_kind: item.preview_kind,
            complete: !!(item.image && item.livephoto),
          },
          folder: {
            folder_name: item.folder_name,
            title: item.title,
            pub_time: item.pub_time,
          },
        },
      ];
      this.viewerIndex = 0;
      this.openViewerEntry(this.viewerSequence[0]);
    },

    buildDetailViewerSequence() {
      return (this.detail.pairs || []).map((pair) => ({
        pair: {
          ...pair,
          item_key: `${this.detail.folder?.folder_name || ""}::${pair.pair_index}`,
        },
        folder: this.detail.folder,
      }));
    },

    buildGalleryViewerSequence() {
      return (this.gallery.items || []).map((galleryItem) => ({
        pair: {
          item_key: galleryItem.item_key || `${galleryItem.folder_name}::${galleryItem.pair_index}`,
          pair_index: galleryItem.pair_index,
          image: galleryItem.image,
          livephoto: galleryItem.livephoto,
          preview_url: galleryItem.preview_url,
          preview_kind: galleryItem.preview_kind,
          complete: !!(galleryItem.image && galleryItem.livephoto),
        },
        folder: {
          folder_name: galleryItem.folder_name,
          title: galleryItem.title,
          pub_time: galleryItem.pub_time,
        },
      }));
    },

    viewerEntryKey(entry) {
      if (!entry) {
        return "";
      }
      return (
        entry.pair?.item_key ||
        `${entry.folder?.folder_name || this.viewer.folder?.folder_name || ""}::${entry.pair?.pair_index || 0}`
      );
    },

    currentViewerEntryKey() {
      return (
        this.viewer.pair?.item_key ||
        `${this.viewer.folder?.folder_name || ""}::${this.viewer.pair?.pair_index || 0}`
      );
    },

    resolvedViewerSequence() {
      return this.viewerSequence || [];
    },

    openViewerFolder() {
      const folderName = this.viewer.folder?.folder_name;
      if (!folderName) {
        return;
      }
      this.closeViewer();
      window.requestAnimationFrame(() => {
        this.openFolder(folderName);
      });
    },

    closeDetail(skipAnimation = false) {
      if (this.viewer.open) {
        this.closeViewer();
      }
      if (!this.detail.open && !this.detailClosing) {
        return;
      }
      if (this.detailCloseTimer) {
        window.clearTimeout(this.detailCloseTimer);
        this.detailCloseTimer = null;
      }
      this.detailRequestId += 1;
      this.detailLoading = false;
      this.detailClosing = !skipAnimation;
      this.detail = { ...this.detail, open: false };
      this.syncBodyLock();
      this.detailCloseTimer = window.setTimeout(() => {
        this.detailClosing = false;
        this.detailCloseTimer = null;
        this.syncBodyLock();
      }, skipAnimation ? 0 : 260);
    },

    closeViewer() {
      if (!this.viewer.open && !this.viewerClosing) {
        return;
      }
      if (this.viewerCloseTimer) {
        window.clearTimeout(this.viewerCloseTimer);
        this.viewerCloseTimer = null;
      }
      this.pauseCurrentViewerMedia(false);
      this.cancelDeleteViewerPair();
      this.viewerSwapPending = false;
      this.viewerPendingDirection = "";
      this.viewerClosing = true;
      this.viewer = { ...this.viewer, open: false };
      this.syncBodyLock();
      this.viewerCloseTimer = window.setTimeout(() => {
        this.viewerImageReady = false;
        this.pauseCurrentViewerMedia(true);
        this.resetViewerTransform();
        this.viewer = { open: false, pair: null, folder: null, showVideo: false };
        this.viewerSource = "detail";
        this.viewerSequence = [];
        this.viewerIndex = 0;
        this.viewerClosing = false;
        this.viewerCloseTimer = null;
        this.syncBodyLock();
      }, 240);
    },

    syncBodyLock() {
      const locked = this.detail.open || this.viewer.open || this.detailClosing || this.viewerClosing || this.taskInspector.open || this.sourcePreview.open;
      const html = document.documentElement;
      const body = document.body;
      body.classList.toggle("detail-layer-open", this.detail.open || this.detailClosing || this.taskInspector.open || this.sourcePreview.open);
      body.classList.toggle("viewer-layer-open", this.viewer.open || this.viewerClosing);
      body.classList.toggle("overlay-locked", locked);
      if (locked) {
        if (this.bodyLockTop !== null) {
          return;
        }
        const scrollTop = window.scrollY || window.pageYOffset || 0;
        const scrollbarWidth = Math.max(window.innerWidth - html.clientWidth, 0);
        this.bodyLockTop = scrollTop;
        this.bodyLockPaddingRight = body.style.paddingRight || "";
        this.bodyLockStyles = {
          htmlOverflow: html.style.overflow || "",
          bodyOverflow: body.style.overflow || "",
          bodyPosition: body.style.position || "",
          bodyTop: body.style.top || "",
          bodyLeft: body.style.left || "",
          bodyRight: body.style.right || "",
          bodyWidth: body.style.width || "",
          bodyPaddingRight: body.style.paddingRight || "",
        };
        html.style.overflow = "hidden";
        body.style.overflow = "hidden";
        body.style.position = "fixed";
        body.style.top = `-${scrollTop}px`;
        body.style.left = "0";
        body.style.right = "0";
        body.style.width = "100%";
        if (scrollbarWidth) {
          body.style.paddingRight = `${scrollbarWidth}px`;
        }
        return;
      }
      if (this.bodyLockTop === null) {
        return;
      }
      const scrollTop = this.bodyLockTop;
      const previousStyles = this.bodyLockStyles || {};
      html.classList.add("scroll-restore-instant");
      html.style.overflow = previousStyles.htmlOverflow || "";
      body.style.overflow = previousStyles.bodyOverflow || "";
      body.style.position = previousStyles.bodyPosition || "";
      body.style.top = previousStyles.bodyTop || "";
      body.style.left = previousStyles.bodyLeft || "";
      body.style.right = previousStyles.bodyRight || "";
      body.style.width = previousStyles.bodyWidth || "";
      body.style.paddingRight = previousStyles.bodyPaddingRight ?? (this.bodyLockPaddingRight || "");
      this.bodyLockTop = null;
      this.bodyLockPaddingRight = "";
      this.bodyLockStyles = null;
      if (scrollTop !== null) {
        window.scrollTo(0, scrollTop);
        document.documentElement.scrollTop = scrollTop;
        document.body.scrollTop = scrollTop;
      }
      const removeInstantRestore = () => html.classList.remove("scroll-restore-instant");
      if (typeof window.requestAnimationFrame === "function") {
        window.requestAnimationFrame(removeInstantRestore);
      } else {
        window.setTimeout(removeInstantRestore, 0);
      }
    },

    cloneDetailPayload(payload) {
      return {
        open: false,
        pairs: (payload?.pairs || []).map((pair) => ({ ...pair })),
        folder: payload?.folder ? { ...payload.folder } : null,
        videos: (payload?.videos || []).map((video) => ({ ...video })),
      };
    },

    cachedDetail(folderName) {
      const cached = this.detailCache[folderName];
      return cached ? this.cloneDetailPayload(cached) : null;
    },

    cacheDetailPayload(folderName, payload) {
      if (!folderName || !payload?.folder) {
        return;
      }
      this.detailCache = {
        ...this.detailCache,
        [folderName]: this.cloneDetailPayload(payload),
      };
    },

    invalidateDetailCache(folderName) {
      if (!folderName || !this.detailCache[folderName]) {
        return;
      }
      const nextCache = { ...this.detailCache };
      delete nextCache[folderName];
      this.detailCache = nextCache;
    },

    updateCachedDetailFavorite(folderName, favorite) {
      const cached = this.detailCache[folderName];
      if (!cached?.folder) {
        return;
      }
      this.detailCache = {
        ...this.detailCache,
        [folderName]: {
          ...cached,
          folder: { ...cached.folder, is_favorite: favorite },
        },
      };
    },

    removeCachedDetailPair(folderName, pairIndex) {
      const cached = this.detailCache[folderName];
      if (!cached) {
        return;
      }
      const pairs = (cached.pairs || []).filter((pair) => Number(pair.pair_index) !== Number(pairIndex));
      const removedPair = (cached.pairs || []).find((pair) => Number(pair.pair_index) === Number(pairIndex));
      const delta = this.pairAssetDelta(removedPair);
      const folder = cached.folder
        ? {
            ...cached.folder,
            image_count: Math.max(0, (cached.folder.image_count || 0) - delta.images),
            livephoto_count: Math.max(0, (cached.folder.livephoto_count || 0) - delta.livephotos),
            asset_count: Math.max(0, (cached.folder.asset_count || 0) - delta.total),
          }
        : cached.folder;
      this.detailCache = {
        ...this.detailCache,
        [folderName]: { ...cached, pairs, folder },
      };
    },

    hoverPreview(video, shouldPlay) {
      if (!video) return;
      if (shouldPlay) {
        video.play().catch(() => {});
        return;
      }
      video.pause();
      video.currentTime = 0;
    },

    startHoverPreview(event) {
      if (!this.hoverPreviewEnabled) {
        return;
      }
      if (this.hoverPreviewTimer) {
        window.clearTimeout(this.hoverPreviewTimer);
        this.hoverPreviewTimer = null;
      }
      this.hoverPreviewCard = event.currentTarget;
      const card = event.currentTarget;
      const video = card.querySelector(".hover-preview-video");
      const image = card.querySelector(".hover-preview-image");
      if (!video) {
        return;
      }
      if (!video.dataset.loaded && video.dataset.src) {
        video.src = video.dataset.src;
        video.dataset.loaded = "1";
      }
      if (image) {
        image.classList.add("hidden");
      }
      video.classList.remove("hidden");
      video.currentTime = 0;
      video.onended = () => this.stopHoverPreviewByCard(card);
      video.play().catch(() => this.stopHoverPreviewByCard(card));
    },

    stopHoverPreview(event) {
      if (this.hoverPreviewTimer) {
        window.clearTimeout(this.hoverPreviewTimer);
        this.hoverPreviewTimer = null;
      }
      this.hoverPreviewCard = null;
      this.stopHoverPreviewByCard(event.currentTarget);
    },

    scheduleHoverPreview(event) {
      if (!this.hoverPreviewEnabled) {
        return;
      }
      const card = event.currentTarget;
      if (this.hoverPreviewTimer) {
        window.clearTimeout(this.hoverPreviewTimer);
      }
      this.hoverPreviewCard = card;
      this.hoverPreviewTimer = window.setTimeout(() => {
        if (this.hoverPreviewCard === card) {
          this.startHoverPreview({ currentTarget: card });
        }
      }, 260);
    },

    cancelScheduledHoverPreview(event) {
      const card = event.currentTarget;
      if (this.hoverPreviewTimer && this.hoverPreviewCard === card) {
        window.clearTimeout(this.hoverPreviewTimer);
        this.hoverPreviewTimer = null;
      }
      this.hoverPreviewCard = null;
      this.stopHoverPreviewByCard(card);
    },

    stopHoverPreviewByCard(card) {
      const video = card.querySelector(".hover-preview-video");
      const image = card.querySelector(".hover-preview-image");
      if (video) {
        video.pause();
        video.currentTime = 0;
        video.classList.add("hidden");
      }
      if (image) {
        image.classList.remove("hidden");
      }
    },

    playbackModeLabel() {
      return {
        loop: "循环",
        pingpong: "乒乓",
        once: "仅播放一次",
        pause: "不播放",
      }[this.playbackMode] || "循环";
    },

    availableMonths() {
      const months = [];
      Object.values(this.meta.years || {}).forEach((group) => {
        group.forEach((month) => months.push(month));
      });
      return months;
    },

    currentMonthLabel(month) {
      if (!month) return "全部时间";
      const [year, monthValue] = month.split("-");
      return `${year}年${Number(monthValue)}月`;
    },

    timeRangeLabel() {
      const months = this.availableMonths();
      if (!months.length) {
        return "全部时间";
      }
      if (this.timeSortMode === "random") {
        return "随机时间";
      }
      const startMonth = this.timeFilterApplied.startMonth;
      const endMonth = this.timeFilterApplied.endMonth;
      if (!startMonth || !endMonth) {
        return "全部时间";
      }
      if (startMonth === endMonth) {
        return this.currentMonthLabel(startMonth);
      }
      return `${this.currentMonthLabel(startMonth)} 至 ${this.currentMonthLabel(endMonth)}`;
    },

    timeSortLabel() {
      return {
        desc: "时间倒序",
        asc: "时间正序",
        random: "随机时间",
      }[this.timeSortMode] || "时间倒序";
    },

    toggleTimeFilter() {
      this.timeFilterOpen = !this.timeFilterOpen;
      if (this.timeFilterOpen) {
        this.syncTimeFilterDraft();
      }
    },

    syncTimeFilterDraft() {
      const months = this.availableMonths();
      if (!months.length) {
        this.timeFilterDraft = { startIndex: 0, endIndex: 0 };
        return;
      }
      const startMonth = this.timeFilterApplied.startMonth || months[0];
      const endMonth = this.timeFilterApplied.endMonth || months[months.length - 1];
      const startIndex = Math.max(months.indexOf(startMonth), 0);
      const endIndex = Math.max(months.indexOf(endMonth), startIndex);
      this.timeFilterDraft = { startIndex, endIndex };
    },

    timeFilterHandleStyle(handle) {
      const months = this.availableMonths();
      const total = Math.max(months.length - 1, 1);
      const index = handle === "start" ? this.timeFilterDraft.startIndex : this.timeFilterDraft.endIndex;
      const progress = total === 0 ? 0 : index / total;
      return `left: ${Math.round(progress * 1000) / 10}%;`;
    },

    timeFilterRangeStyle() {
      const months = this.availableMonths();
      const total = Math.max(months.length - 1, 1);
      const start = total === 0 ? 0 : this.timeFilterDraft.startIndex / total;
      const end = total === 0 ? 0 : this.timeFilterDraft.endIndex / total;
      return `left: ${Math.round(start * 1000) / 10}%; width: ${Math.max((end - start) * 100, 2)}%;`;
    },

    timeFilterSummary() {
      const months = this.availableMonths();
      if (!months.length) {
        return "暂无可筛选时间";
      }
      const startMonth = months[this.timeFilterDraft.startIndex];
      const endMonth = months[this.timeFilterDraft.endIndex];
      if (!startMonth || !endMonth) {
        return "全部时间";
      }
      if (startMonth === endMonth) {
        return this.currentMonthLabel(startMonth);
      }
      return `${this.currentMonthLabel(startMonth)} 至 ${this.currentMonthLabel(endMonth)}`;
    },

    timeFilterYearMarks() {
      const months = this.availableMonths();
      const total = Math.max(months.length - 1, 1);
      const entries = Object.keys(this.meta.years || {}).map((year) => {
        const firstMonth = (this.meta.years[year] || [])[0];
        const index = Math.max(months.indexOf(firstMonth), 0);
        return {
          year,
          progress: index / total,
        };
      });
      const filtered = [];
      let lastProgress = -1;
      entries.forEach((entry, index) => {
        const isEdge = index === 0 || index === entries.length - 1;
        if (!isEdge && entry.progress - lastProgress < 0.12) {
          return;
        }
        lastProgress = entry.progress;
        filtered.push({
          year: entry.year,
          style: `left: ${Math.round(entry.progress * 1000) / 10}%;`,
        });
      });
      return filtered;
    },

    timeFilterMonthTicks() {
      const months = this.availableMonths();
      const total = Math.max(months.length - 1, 1);
      return months.map((month, index) => ({
        month,
        style: `left: ${Math.round((index / total) * 1000) / 10}%;`,
      }));
    },

    timeFilterPointerDown(event, handle) {
      event.preventDefault();
      this.timeFilterDrag = { active: true, handle };
      this.updateTimeFilterFromPoint(event.clientX);
    },

    timeFilterPointerMove(event) {
      if (!this.timeFilterDrag.active) {
        return;
      }
      this.updateTimeFilterFromPoint(event.clientX);
    },

    finishTimeFilterDrag() {
      if (!this.timeFilterDrag.active) {
        return;
      }
      this.timeFilterDrag = { active: false, handle: null };
      this.commitTimeFilter();
    },

    updateTimeFilterFromPoint(clientX) {
      const zone = document.querySelector(".time-filter-track");
      const months = this.availableMonths();
      if (!zone || !months.length) {
        return;
      }
      const rect = zone.getBoundingClientRect();
      const relative = Math.max(0, Math.min(1, (clientX - rect.left) / Math.max(rect.width, 1)));
      const index = Math.round(relative * Math.max(months.length - 1, 1));
      if (this.timeFilterDrag.handle === "start") {
        this.timeFilterDraft.startIndex = Math.min(index, this.timeFilterDraft.endIndex);
        return;
      }
      this.timeFilterDraft.endIndex = Math.max(index, this.timeFilterDraft.startIndex);
    },

    timeFilterWheel(event) {
      const months = this.availableMonths();
      if (months.length <= 1) {
        return;
      }
      event.preventDefault();
      const step = event.deltaY > 0 ? 1 : -1;
      if (event.shiftKey) {
        this.timeFilterDraft.endIndex = Math.max(
          this.timeFilterDraft.startIndex,
          Math.min(months.length - 1, this.timeFilterDraft.endIndex + step),
        );
      } else {
        const span = this.timeFilterDraft.endIndex - this.timeFilterDraft.startIndex;
        let nextStart = Math.max(0, Math.min(months.length - 1 - span, this.timeFilterDraft.startIndex + step));
        let nextEnd = nextStart + span;
        if (nextEnd > months.length - 1) {
          nextEnd = months.length - 1;
          nextStart = Math.max(0, nextEnd - span);
        }
        this.timeFilterDraft.startIndex = nextStart;
        this.timeFilterDraft.endIndex = nextEnd;
      }
      this.scheduleTimeFilterCommit();
    },

    scheduleTimeFilterCommit() {
      if (this.timeFilterApplyTimer) {
        window.clearTimeout(this.timeFilterApplyTimer);
      }
      this.timeFilterApplyTimer = window.setTimeout(() => {
        this.commitTimeFilter();
      }, 140);
    },

    async commitTimeFilter() {
      if (this.timeFilterApplyTimer) {
        window.clearTimeout(this.timeFilterApplyTimer);
        this.timeFilterApplyTimer = null;
      }
      const months = this.availableMonths();
      if (!months.length) {
        return;
      }
      const startMonth = months[this.timeFilterDraft.startIndex] || null;
      const endMonth = months[this.timeFilterDraft.endIndex] || null;
      const applyingFullRange = this.timeFilterDraft.startIndex === 0 && this.timeFilterDraft.endIndex === months.length - 1;
      const currentStart = this.timeFilterApplied.startMonth || months[0];
      const currentEnd = this.timeFilterApplied.endMonth || months[months.length - 1];
      if (startMonth === currentStart && endMonth === currentEnd) {
        return;
      }
      this.timeFilterApplied = applyingFullRange
        ? { startMonth: null, endMonth: null }
        : { startMonth, endMonth };
      window.scrollTo({ top: 0, behavior: "smooth" });
      await this.refreshGallery(true);
    },

    async clearTimeFilter() {
      const months = this.availableMonths();
      if (!months.length) {
        return;
      }
      this.timeFilterApplied = { startMonth: null, endMonth: null };
      this.timeFilterDraft = { startIndex: 0, endIndex: months.length - 1 };
      window.scrollTo({ top: 0, behavior: "smooth" });
      await this.refreshGallery(true);
    },

    reviewSourceUrl(item) {
      if (item?.original_url) {
        return item.original_url;
      }
      const dynamicId = item.source_dynamic_id || item.top_dynamic_id;
      if (dynamicId && String(dynamicId).startsWith("site:")) {
        return "";
      }
      return dynamicId ? `https://www.bilibili.com/opus/${dynamicId}` : "";
    },

    openReviewSource(item) {
      const url = this.reviewSourceUrl(item);
      if (!url) {
        this.notify("error", "无法打开原始动态", "当前待审核项没有可用的动态编号。");
        return;
      }
      if (this.settings?.review_source_open_mode === "popup") {
        this.sourcePreview = {
          open: true,
          url,
          title: item?.folder_name_candidate || item?.title || "原始内容",
          subtitle: url,
        };
        this.syncBodyLock();
        return;
      }
      this.openExternalUrl(url);
    },

    openExternalUrl(url) {
      window.open(url, "_blank", "noopener,noreferrer");
    },

    openSourcePreviewExternal() {
      if (this.sourcePreview.url) {
        this.openExternalUrl(this.sourcePreview.url);
      }
    },

    closeSourcePreview() {
      if (!this.sourcePreview.open) {
        return;
      }
      this.sourcePreview = { open: false, url: "", title: "", subtitle: "" };
      this.syncBodyLock();
    },

    openTrashSource(item) {
      this.openReviewSource(item.folder || item);
    },

    cyclePlayback() {
      const index = this.playbackModes.indexOf(this.playbackMode);
      this.playbackMode = this.playbackModes[(index + 1) % this.playbackModes.length];
      localStorage.setItem("livephoto_playback_mode", this.playbackMode);
      document.querySelectorAll(".viewer-video").forEach((video) => this.applyPlaybackMode(video, true));
    },

    toggleViewerPlayback() {
      if (!this.viewer.pair?.livephoto) {
        return;
      }
      if (this.viewer.showVideo) {
        this.pauseCurrentViewerMedia(true);
        if (this.viewer.pair?.image) {
          this.viewer.showVideo = false;
        }
        return;
      }
      const video = document.querySelector(".viewer-video");
      if (!video || video.dataset.viewerToken !== String(this.viewerToken)) {
        return;
      }
      this.viewer.showVideo = true;
      this.$nextTick(() => this.applyPlaybackMode(video, true));
    },

    viewerVisibleMedia() {
      return document.querySelector(".viewer-stage-image:not(.hidden), .viewer-stage-preview:not(.hidden), .viewer-video:not(.hidden)");
    },

    pointInsideRect(clientX, clientY, rect) {
      return clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom;
    },

    viewerMediaDisplayRect(stage, media) {
      const stageRect = stage?.getBoundingClientRect?.() || media.getBoundingClientRect();
      const naturalWidth = media.tagName === "VIDEO" ? (media.videoWidth || media.clientWidth) : (media.naturalWidth || media.clientWidth);
      const naturalHeight = media.tagName === "VIDEO" ? (media.videoHeight || media.clientHeight) : (media.naturalHeight || media.clientHeight);
      if (!naturalWidth || !naturalHeight) {
        return media.getBoundingClientRect();
      }
      const scale = Math.min(stageRect.width / naturalWidth, stageRect.height / naturalHeight);
      const displayWidth = naturalWidth * scale;
      const displayHeight = naturalHeight * scale;
      const left = stageRect.left + (stageRect.width - displayWidth) / 2;
      const top = stageRect.top + (stageRect.height - displayHeight) / 2;
      return {
        left,
        top,
        right: left + displayWidth,
        bottom: top + displayHeight,
      };
    },

    handleViewerTap(clientX, clientY, stage = null) {
      if (this.viewerZoom > 1) {
        return;
      }
      const media = this.viewerVisibleMedia();
      if (media) {
        const mediaRect = this.viewerMediaDisplayRect(stage, media);
        if (this.pointInsideRect(clientX, clientY, mediaRect)) {
          if (this.viewer.pair?.livephoto) {
            this.toggleViewerPlayback();
          }
          return;
        }
      }
      if (stage) {
        const stageRect = stage.getBoundingClientRect();
        if (this.pointInsideRect(clientX, clientY, stageRect)) {
          this.closeViewer();
          return;
        }
      }
      this.closeViewer();
    },

    queueViewerTap(clientX, clientY, stage) {
      if (this.viewerClickTimer) {
        window.clearTimeout(this.viewerClickTimer);
      }
      this.viewerClickTimer = window.setTimeout(() => {
        this.viewerClickTimer = null;
        this.handleViewerTap(clientX, clientY, stage);
      }, 220);
    },

    applyPlaybackMode(video, restart = false) {
      const forward = video.dataset.forward;
      const reverse = video.dataset.reverse;
      const hasImage = video.dataset.hasImage === "1";
      const viewerToken = String(this.viewerToken);
      const currentForward = this.viewer.pair?.livephoto?.url || "";
      if (!forward || video.dataset.viewerToken !== viewerToken || forward !== currentForward) return;
      video.loop = false;
      video.onended = null;
      if (this.playbackMode === "pause") {
        this.viewer.showVideo = false;
        video.pause();
        video.removeAttribute("src");
        video.load();
        video.setAttribute("poster", video.getAttribute("poster") || "");
        return;
      }
      this.viewer.showVideo = true;
      if (!video.src || restart) {
        video.src = forward;
      }
      if (this.playbackMode === "loop") {
        video.loop = true;
        if (restart) video.currentTime = 0;
        video.play().catch(() => {});
        return;
      }
      if (this.playbackMode === "once") {
        video.onended = () => {
          if (video.dataset.viewerToken !== String(this.viewerToken)) {
            return;
          }
          if (hasImage) {
            this.viewer.showVideo = false;
          }
        };
        if (restart) video.currentTime = 0;
        video.play().catch(() => {});
        return;
      }
      if (this.playbackMode === "pingpong") {
        if (!reverse) {
          video.loop = true;
          video.play().catch(() => {});
          return;
        }
        video.onended = () => {
          if (video.dataset.viewerToken !== String(this.viewerToken)) {
            return;
          }
          video.src = video.src.endsWith(reverse) ? forward : reverse;
          video.load();
          video.play().catch(() => {});
        };
        if (restart) {
          video.src = forward;
          video.load();
        }
        video.play().catch(() => {});
      }
    },

    replayViewerOnce() {
      if (this.playbackMode !== "once" || !this.viewer.pair?.livephoto || this.viewer.showVideo) {
        return;
      }
      const video = document.querySelector(".viewer-video");
      if (!video || video.dataset.viewerToken !== String(this.viewerToken)) {
        return;
      }
      this.viewer.showVideo = true;
      this.$nextTick(() => this.applyPlaybackMode(video, true));
    },

    currentViewerSequenceIndex(sequence = this.resolvedViewerSequence()) {
      const currentKey = this.currentViewerEntryKey();
      const currentIndex = (sequence || []).findIndex((entry) => this.viewerEntryKey(entry) === currentKey);
      if (currentIndex >= 0) {
        return currentIndex;
      }
      const fallbackIndex = Number(this.viewerIndex);
      return Number.isInteger(fallbackIndex) && fallbackIndex >= 0 && fallbackIndex < (sequence || []).length
        ? fallbackIndex
        : -1;
    },

    canShowPreviousPair() {
      return this.currentViewerSequenceIndex() > 0;
    },

    canShowNextPair() {
      const sequence = this.resolvedViewerSequence();
      const currentIndex = this.currentViewerSequenceIndex(sequence);
      return currentIndex >= 0 && currentIndex < sequence.length - 1;
    },

    showPreviousPair() {
      const sequence = this.resolvedViewerSequence();
      const currentIndex = this.currentViewerSequenceIndex(sequence);
      if (currentIndex <= 0) {
        return;
      }
      this.pauseCurrentViewerMedia(true);
      this.viewerSequence = sequence;
      this.viewerIndex = currentIndex - 1;
      this.openViewerEntry(sequence[this.viewerIndex], true, false, "right");
    },

    showNextPair() {
      const sequence = this.resolvedViewerSequence();
      const currentIndex = this.currentViewerSequenceIndex(sequence);
      if (currentIndex < 0 || currentIndex >= sequence.length - 1) {
        return;
      }
      this.pauseCurrentViewerMedia(true);
      this.viewerSequence = sequence;
      this.viewerIndex = currentIndex + 1;
      this.openViewerEntry(sequence[this.viewerIndex], true, false, "left");
    },

    pauseCurrentViewerMedia(resetSource = false) {
      this.viewer.showVideo = false;
      if (this.viewerPlaybackTimer) {
        window.clearTimeout(this.viewerPlaybackTimer);
        this.viewerPlaybackTimer = null;
      }
      if (this.viewerClickTimer) {
        window.clearTimeout(this.viewerClickTimer);
        this.viewerClickTimer = null;
      }
      document.querySelectorAll(".viewer-video").forEach((video) => {
        video.pause();
        video.currentTime = 0;
        video.onended = null;
        if (resetSource) {
          video.removeAttribute("src");
          video.load();
        }
      });
    },

    animateViewerSwitch(direction) {
      this.viewerSwitchDirection = direction;
      if (this.viewerSwitchTimer) {
        window.clearTimeout(this.viewerSwitchTimer);
      }
      this.viewerSwitchTimer = window.setTimeout(() => {
        this.viewerSwitchDirection = "";
      }, 280);
    },

    resetViewerTransform() {
      this.viewerZoom = 1;
      this.viewerOffsetX = 0;
      this.viewerOffsetY = 0;
      this.viewerTransitionEnabled = true;
      this.viewerWheelOffset = 0;
      if (this.viewerWheelTimer) {
        window.clearTimeout(this.viewerWheelTimer);
        this.viewerWheelTimer = null;
      }
      if (this.viewerPlaybackTimer) {
        window.clearTimeout(this.viewerPlaybackTimer);
        this.viewerPlaybackTimer = null;
      }
      if (this.viewerClickTimer) {
        window.clearTimeout(this.viewerClickTimer);
        this.viewerClickTimer = null;
      }
      this.viewerGesture = {
        pointers: {},
        startX: 0,
        startY: 0,
        startOffsetX: 0,
        startOffsetY: 0,
        startZoom: 1,
        startDistance: 0,
        active: false,
        isPinch: false,
        moved: false,
      };
    },

    viewerMediaLoaded(kind, event) {
      const target = event?.target;
      if (!this.viewer.open || !target) {
        return;
      }
      if (kind === "image") {
        this.viewerImageReady = true;
      }
      if (kind === "video" && target.dataset.viewerToken !== String(this.viewerToken)) {
        return;
      }
      if (this.viewerSwapPending) {
        const direction = this.viewerPendingDirection;
        this.viewerSwapPending = false;
        this.viewerPendingDirection = "";
        if (direction) {
          this.animateViewerSwitch(direction);
        }
      }
      if (kind === "image" && this.viewer.pair?.livephoto && !this.viewer.showVideo && this.playbackMode !== "pause") {
        this.scheduleViewerPlaybackStart();
      }
    },

    viewerMediaStyle() {
      return `transform: translate3d(${this.viewerOffsetX}px, ${this.viewerOffsetY}px, 0) scale(${this.viewerZoom});`;
    },

    viewerShouldShowImageWash() {
      return !!(this.viewer.pair?.image && !this.viewerImageReady && !(this.viewer.showVideo && this.viewer.pair?.livephoto));
    },

    viewerPreviewUrl() {
      return (
        this.viewer.pair?.image?.thumb_url ||
        this.viewer.pair?.preview_url ||
        this.viewer.pair?.livephoto?.thumb_url ||
        this.viewer.pair?.livephoto?.cover_url ||
        this.viewer.pair?.image?.url ||
        ""
      );
    },

    viewerStageClick(event) {
      event.stopPropagation();
      if (Date.now() < this.viewerSyntheticTapUntil) {
        return;
      }
      if (this.viewerZoom > 1) {
        return;
      }
      this.queueViewerTap(event.clientX, event.clientY, event.currentTarget);
    },

    viewerDoubleClick(event) {
      event.preventDefault();
      event.stopPropagation();
      if (this.viewerClickTimer) {
        window.clearTimeout(this.viewerClickTimer);
        this.viewerClickTimer = null;
      }
      if (this.viewerZoom > 1) {
        this.resetViewerTransform();
        return;
      }
      const stage = event.currentTarget;
      const stageRect = stage.getBoundingClientRect();
      const offsetX = event.clientX - (stageRect.left + stageRect.width / 2);
      const offsetY = event.clientY - (stageRect.top + stageRect.height / 2);
      this.viewerZoom = 2;
      this.viewerOffsetX = -offsetX * 0.8;
      this.viewerOffsetY = -offsetY * 0.8;
      this.viewerTransitionEnabled = true;
    },

    viewerShellClick(event) {
      if (event.target.closest(".viewer-floating")) {
        return;
      }
      if (event.target.closest(".viewer-media")) {
        return;
      }
      this.closeViewer();
    },

    viewerWheel(event) {
      if (this.viewerZoom > 1 || this.viewerGesture.active || this.viewerGesture.isPinch) {
        return;
      }
      const dominantVertical = Math.abs(event.deltaY) > Math.abs(event.deltaX) * 1.2;
      if (!dominantVertical) {
        return;
      }
      event.preventDefault();
      this.viewerWheelOffset += event.deltaY;
      this.viewerOffsetY = Math.max(-180, Math.min(180, this.viewerWheelOffset * 0.32));
      if (this.viewerWheelTimer) {
        window.clearTimeout(this.viewerWheelTimer);
      }
      this.viewerWheelTimer = window.setTimeout(() => {
        this.viewerWheelOffset = 0;
        if (!this.viewer.open) {
          return;
        }
        this.viewerOffsetY = 0;
      }, 180);
      if (Math.abs(this.viewerWheelOffset) > 260) {
        this.closeViewer();
      }
    },

    viewerPointerDown(event) {
      if (event.currentTarget?.setPointerCapture) {
        event.currentTarget.setPointerCapture(event.pointerId);
      }
      this.viewerTransitionEnabled = false;
      const pointers = { ...this.viewerGesture.pointers, [event.pointerId]: { x: event.clientX, y: event.clientY } };
      this.viewerGesture.pointers = pointers;
      const values = Object.values(pointers);
      if (values.length === 2) {
        this.viewerGesture.isPinch = true;
        this.viewerGesture.startDistance = this.pointerDistance(values[0], values[1]);
        this.viewerGesture.startZoom = this.viewerZoom;
        return;
      }
      this.viewerGesture.active = true;
      this.viewerGesture.isPinch = false;
      this.viewerGesture.startX = event.clientX;
      this.viewerGesture.startY = event.clientY;
      this.viewerGesture.startOffsetX = this.viewerOffsetX;
      this.viewerGesture.startOffsetY = this.viewerOffsetY;
      this.viewerGesture.moved = false;
    },

    viewerPointerMove(event) {
      if (!(event.pointerId in this.viewerGesture.pointers)) {
        return;
      }
      this.viewerGesture.pointers[event.pointerId] = { x: event.clientX, y: event.clientY };
      const values = Object.values(this.viewerGesture.pointers);
      if (values.length === 2 && this.viewerGesture.startDistance > 0) {
        const distance = this.pointerDistance(values[0], values[1]);
        const zoom = Math.max(1, Math.min(4, this.viewerGesture.startZoom * (distance / this.viewerGesture.startDistance)));
        this.viewerZoom = zoom;
        if (zoom === 1) {
          this.viewerOffsetX = 0;
          this.viewerOffsetY = 0;
        }
        return;
      }
      if (!this.viewerGesture.active) {
        return;
      }
      const deltaX = event.clientX - this.viewerGesture.startX;
      const deltaY = event.clientY - this.viewerGesture.startY;
      if (Math.abs(deltaX) > 8 || Math.abs(deltaY) > 8) {
        this.viewerGesture.moved = true;
      }
      if (this.viewerZoom > 1) {
        this.viewerOffsetX = this.viewerGesture.startOffsetX + deltaX;
        this.viewerOffsetY = this.viewerGesture.startOffsetY + deltaY;
        return;
      }
      this.viewerOffsetX = deltaX * 0.35;
      this.viewerOffsetY = deltaY * 0.35;
    },

    viewerPointerUp(event) {
      const wasPinch = this.viewerGesture.isPinch;
      if (event.currentTarget?.releasePointerCapture) {
        try {
          event.currentTarget.releasePointerCapture(event.pointerId);
        } catch (error) {
          void error;
        }
      }
      const pointer = this.viewerGesture.pointers[event.pointerId];
      delete this.viewerGesture.pointers[event.pointerId];
      if (!pointer) {
        return;
      }
      if (Object.keys(this.viewerGesture.pointers).length >= 1) {
        return;
      }
      const deltaX = event.clientX - this.viewerGesture.startX;
      const deltaY = event.clientY - this.viewerGesture.startY;
      const absX = Math.abs(deltaX);
      const absY = Math.abs(deltaY);
      if (this.viewerZoom === 1 && !wasPinch) {
        if (absY > 180 && absY > absX * 1.2) {
          this.closeViewer();
        } else if (absX > 120 && absX > absY * 1.2) {
          if (deltaX < 0) {
            this.showNextPair();
          } else {
            this.showPreviousPair();
          }
        } else if (!this.viewerGesture.moved && event.pointerType !== "mouse") {
          this.viewerSyntheticTapUntil = Date.now() + 220;
          this.handleViewerTap(event.clientX, event.clientY, event.currentTarget);
        }
      }
      this.viewerGesture.active = false;
      this.viewerGesture.isPinch = false;
      if (this.viewerZoom === 1) {
        this.viewerOffsetX = 0;
        this.viewerOffsetY = 0;
      }
      window.requestAnimationFrame(() => {
        this.viewerTransitionEnabled = true;
      });
    },

    pointerDistance(left, right) {
      const deltaX = left.x - right.x;
      const deltaY = left.y - right.y;
      return Math.sqrt(deltaX * deltaX + deltaY * deltaY);
    },

    async refreshReview() {
      const payload = await this.api("/api/review/items");
      this.reviewItems = payload.items;
      this.lazyLoaded.review = true;
      this.sidebarCounts = { ...this.sidebarCounts, review: this.reviewItems.length };
    },

    async refreshTasks() {
      const payload = await this.api("/api/tasks/runs");
      this.taskRuns = payload.items;
      this.queuedTasks = payload.queue || [];
      this.lazyLoaded.tasks = true;
      this.sidebarCounts = { ...this.sidebarCounts, tasks: this.taskRuns.length };
      if (this.queuedCancelConfirmId && !this.queuedTasks.some((item) => Number(item.queue_id) === this.queuedCancelConfirmId)) {
        this.queuedCancelConfirmId = null;
      }
    },

    formatInspectorJson(payload) {
      try {
        return JSON.stringify(payload || {}, null, 2);
      } catch (error) {
        return String(payload || "");
      }
    },

    formatAddedItems(items) {
      const rows = Array.isArray(items) ? items : [];
      if (!rows.length) {
        return "本次没有新增内容。";
      }
      return rows
        .map((item, index) => {
          const lines = [
            `${index + 1}. ${item.title || `动态 ${item.top_dynamic_id}`}`,
            `   订阅: ${item.subscription_name || item.subscription_uid || "默认订阅"}`,
            `   时间: ${item.pub_time || "-"}`,
            `   类型: ${item.change_type === "updated" ? "补同步/更新" : "新增"}`,
            `   静态图: ${item.image_count || 0} · Live Photo: ${item.livephoto_count || 0} · 文件: ${item.saved_files || 0}`,
            `   动态ID: ${item.top_dynamic_id || "-"}`,
          ];
          return lines.join("\n");
        })
        .join("\n\n");
    },

    openCurrentTaskInspector() {
      this.taskInspector = {
        open: true,
        title: this.pullStatus.running ? "当前运行任务" : "当前状态",
        subtitle: this.pullStatus.message || "空闲",
        body: this.formatInspectorJson({
          mode: this.pullStatus.mode,
          running: this.pullStatus.running,
          paused: this.pullStatus.paused,
          cancel_requested: this.pullStatus.cancel_requested,
          progress: this.pullStatus.progress,
          current_source: this.pullStatus.current_source,
          current_post: this.pullStatus.current_post,
          site_detail: this.pullStatus.site_detail || {},
          stats: this.pullStatus.stats || {},
          counters: this.pullStatus.counters || {},
          events: this.pullStatus.events || [],
          queue: this.pullStatus.queue || [],
        }),
      };
      this.taskInspectorLoading = false;
      this.syncBodyLock();
    },

    openCurrentAddedItems() {
      const items = this.pullStatus?.stats?.added_items || [];
      this.taskInspector = {
        open: true,
        title: "本次新增内容",
        subtitle: this.pullStatus.message || "当前任务",
        body: this.formatAddedItems(items),
      };
      this.taskInspectorLoading = false;
      this.syncBodyLock();
    },

    async openTaskInspector(item) {
      this.taskInspectorLoading = true;
      this.taskInspector = {
        open: true,
        title: `${item.task_type} #${item.id}`,
        subtitle: item.message || item.status,
        body: "正在加载日志与执行细节...",
      };
      this.syncBodyLock();
      try {
        const payload = await this.api(`/api/tasks/${item.id}`);
        const task = payload.item || item;
        this.taskInspector = {
          open: true,
          title: `${task.task_type} #${task.id}`,
          subtitle: task.message || task.status,
          body: this.formatInspectorJson({
            status: task.status,
            created_at: task.created_at,
            finished_at: task.finished_at,
            details: task.details || {},
          }),
        };
      } catch (error) {
        this.taskInspector = {
          open: true,
          title: `${item.task_type} #${item.id}`,
          subtitle: item.message || item.status,
          body: `加载任务详情失败：${error.message}`,
        };
      } finally {
        this.taskInspectorLoading = false;
      }
    },

    async openTaskAddedItems(item) {
      this.taskInspectorLoading = true;
      this.taskInspector = {
        open: true,
        title: `任务 #${item.id} 的新增内容`,
        subtitle: item.message || item.status,
        body: "正在加载本次新增列表...",
      };
      this.syncBodyLock();
      try {
        const payload = await this.api(`/api/tasks/${item.id}`);
        const task = payload.item || item;
        const items = task?.details?.added_items || [];
        this.taskInspector = {
          open: true,
          title: `任务 #${task.id} 的新增内容`,
          subtitle: task.message || task.status,
          body: this.formatAddedItems(items),
        };
      } catch (error) {
        this.taskInspector = {
          open: true,
          title: `任务 #${item.id} 的新增内容`,
          subtitle: item.message || item.status,
          body: `加载新增内容失败：${error.message}`,
        };
      } finally {
        this.taskInspectorLoading = false;
      }
    },

    openQueuedTaskInspector(item) {
      this.taskInspector = {
        open: true,
        title: `排队任务 #${item.queue_id}`,
        subtitle: item.label || item.kind,
        body: this.formatInspectorJson({
          kind: item.kind,
          label: item.label,
          position: item.position,
          queued_at: item.queued_at,
          payload: item.payload || {},
        }),
      };
      this.taskInspectorLoading = false;
      this.syncBodyLock();
    },

    closeTaskInspector() {
      this.taskInspector = { open: false, title: "", subtitle: "", body: "" };
      this.taskInspectorLoading = false;
      this.syncBodyLock();
    },

    taskHasAddedItems(item) {
      return Array.isArray(item?.details?.added_items) && item.details.added_items.length > 0;
    },

    currentTaskHasAddedItems() {
      return Array.isArray(this.pullStatus?.stats?.added_items) && this.pullStatus.stats.added_items.length > 0;
    },

    taskModeLabel(mode) {
      const labels = {
        pull: "拉取",
        "subscription-pull": "订阅拉取",
        "subscription-reload": "全量订阅",
        review: "待审核",
        validate: "校验",
        index: "索引",
        "site-sync": "站点同步",
        "site-validate": "站点校验",
        startup: "启动整理",
        idle: "空闲",
      };
      return labels[mode] || mode || "任务";
    },

    taskProgressValue(status) {
      const explicit = Number(status?.progress);
      if (Number.isFinite(explicit)) {
        return Math.max(0, Math.min(100, explicit));
      }
      const processed = Number(status?.processed);
      const total = Number(status?.total);
      if (Number.isFinite(processed) && Number.isFinite(total) && total > 0) {
        return Math.max(0, Math.min(100, Math.round((processed / total) * 100)));
      }
      return status?.running ? 8 : 0;
    },

    taskProgressText(status) {
      const processed = Number(status?.processed);
      const total = Number(status?.total);
      if (Number.isFinite(processed) && Number.isFinite(total) && total > 0) {
        return `${Math.min(processed, total)} / ${total} · ${this.taskProgressValue(status)}%`;
      }
      return status?.running ? "正在准备任务细节" : "无运行任务";
    },

    taskCounterTags(status) {
      const stats = status?.stats || {};
      const counters = status?.counters || status?.site_detail?.counters || {};
      const rows = [
        ["发现", counters.discovered ?? stats.matched],
        ["入库", counters.posts ?? stats.downloaded_candidates],
        ["下载", counters.downloaded ?? stats.saved_files],
        ["拦截", counters.blocked ?? stats.review_candidates],
        ["跳过", counters.skipped ?? stats.skipped],
        ["失败", counters.errors ?? stats.errors],
      ];
      return rows
        .filter(([, value]) => value !== undefined && value !== null)
        .map(([label, value]) => ({ label, value: Number(value) || 0 }));
    },

    async pauseTask() {
      this.setImmediateTaskFeedback("正在暂停当前任务...", { paused: true });
      const result = await this.api("/api/tasks/pause", { method: "POST" });
      await this.refreshStatus();
      await this.refreshTasks();
      this.notify("info", "任务已暂停", result.message);
    },

    async resumeTask() {
      this.setImmediateTaskFeedback("正在继续当前任务...", { paused: false });
      const result = await this.api("/api/tasks/resume", { method: "POST" });
      await this.refreshStatus();
      await this.refreshTasks();
      this.notify("success", "任务已继续", result.message);
    },

    async cancelTask() {
      this.setImmediateTaskFeedback("正在请求取消当前任务...", { cancel_requested: true });
      const result = await this.api("/api/tasks/cancel", { method: "POST" });
      await this.refreshStatus();
      await this.refreshTasks();
      this.notify("info", "已请求取消", result.message);
    },

    clearTaskLogsButtonLabel() {
      return this.clearTaskLogsConfirmStep === 0 ? "清理已结束日志" : "再次确认清理";
    },

    askClearTaskLogs() {
      this.clearTaskLogsConfirmStep = Math.min(this.clearTaskLogsConfirmStep + 1, 1);
    },

    cancelClearTaskLogs() {
      this.clearTaskLogsConfirmStep = 0;
    },

    async confirmClearTaskLogs() {
      if (this.clearTaskLogsConfirmStep < 1) {
        return;
      }
      const previousTaskRuns = [...(this.taskRuns || [])];
      this.taskRuns = (this.taskRuns || []).filter((item) => item.status === "running");
      this.clearTaskLogsConfirmStep = 0;
      this.notify("info", "正在清理任务日志", "页面已先更新，后台正在处理。");
      try {
        const result = await this.api("/api/tasks/clear-finished", { method: "POST" });
        await this.refreshTasks();
        this.notify("success", "任务日志已清理", result.message);
      } catch (error) {
        this.taskRuns = previousTaskRuns;
        this.notify("error", "清理失败", error.message || "任务日志已恢复。");
      }
    },

    async refreshTrash() {
      const payload = await this.api("/api/trash/items");
      this.trashItems = payload.items;
      this.lazyLoaded.trash = true;
      this.sidebarCounts = { ...this.sidebarCounts, trash: this.trashItems.length };
      const previousExpanded = { ...(this.trashGroupExpanded || {}) };
      this.trashGroupExpanded = Object.fromEntries(
        this.trashGroups().map((group) => [group.key, previousExpanded[group.key] ?? false]),
      );
    },

    trashGroupKey(item) {
      const uid = String(item?.subscription_uid || "").trim();
      if (uid) {
        return uid;
      }
      const name = String(item?.subscription_name || "").trim();
      return name ? `name:${name}` : "unknown";
    },

    trashGroups() {
      const groups = new Map();
      for (const item of this.trashItems || []) {
        const key = this.trashGroupKey(item);
        const uid = String(item?.subscription_uid || "").trim();
        const name = String(item?.subscription_name || "").trim()
          || (uid.startsWith("site:") ? "站点订阅" : uid ? `UID ${uid}` : "未归属内容");
        if (!groups.has(key)) {
          groups.set(key, {
            key,
            uid,
            name,
            is_site: uid.startsWith("site:"),
            latest_deleted_at: item.deleted_at || "",
            items: [],
          });
        }
        const group = groups.get(key);
        group.items.push(item);
        if (String(item.deleted_at || "") > String(group.latest_deleted_at || "")) {
          group.latest_deleted_at = item.deleted_at || "";
        }
      }
      return [...groups.values()].sort((left, right) => String(right.latest_deleted_at || "").localeCompare(String(left.latest_deleted_at || "")));
    },

    isTrashGroupExpanded(key) {
      return this.trashGroupExpanded[String(key)] === true;
    },

    toggleTrashGroup(key) {
      const normalized = String(key);
      this.trashGroupExpanded = {
        ...this.trashGroupExpanded,
        [normalized]: !this.isTrashGroupExpanded(normalized),
      };
    },

    trashGroupIconUrl(group) {
      if (!group?.uid) {
        return "";
      }
      const item = (this.subscriptions || []).find((entry) => String(entry.uid) === String(group.uid));
      return item ? this.subscriptionIconUrl(item) : "";
    },

    currentViewerDeleteKey() {
      if (!this.viewer.folder?.folder_name || !this.viewer.pair?.pair_index) {
        return null;
      }
      return `${this.viewer.folder.folder_name}::${this.viewer.pair.pair_index}`;
    },

    pairDeleteKey(folderName, pairIndex) {
      if (!folderName || !pairIndex) {
        return null;
      }
      return `${folderName}::${pairIndex}`;
    },

    pairDeletePending(folderName, pairIndex) {
      return this.deletePairConfirmKey === this.pairDeleteKey(folderName, pairIndex) && this.deletePairConfirmStep >= 1;
    },

    deletePairButtonLabel() {
      if (this.deletePairConfirmStep === 0) {
        return "删除";
      }
      return "确认永久删除";
    },

    askDeleteViewerPair() {
      const key = this.currentViewerDeleteKey();
      if (!key) {
        return;
      }
      this.askDeletePair(this.viewer.folder.folder_name, this.viewer.pair.pair_index);
    },

    askDeletePair(folderName, pairIndex) {
      const key = this.pairDeleteKey(folderName, pairIndex);
      if (!key) {
        return;
      }
      this.deletePairConfirmKey = key;
      this.deletePairConfirmStep = 1;
    },

    cancelDeleteViewerPair() {
      this.deletePairConfirmKey = null;
      this.deletePairConfirmStep = 0;
    },

    async confirmDeleteViewerPair() {
      const folderName = this.viewer.folder?.folder_name;
      const pairIndex = this.viewer.pair?.pair_index;
      const key = this.currentViewerDeleteKey();
      if (!folderName || !pairIndex || this.deletePairConfirmKey !== key || this.deletePairConfirmStep < 1) {
        return;
      }
      await this.confirmDeletePair(folderName, pairIndex);
    },

    pairAssetDelta(pair) {
      const hasImage = !!(pair?.image || pair?.has_images);
      const hasLivephoto = !!(pair?.livephoto || pair?.has_livephoto);
      return {
        images: hasImage ? 1 : 0,
        livephotos: hasLivephoto ? 1 : 0,
        total: (hasImage ? 1 : 0) + (hasLivephoto ? 1 : 0),
      };
    },

    async confirmDeletePair(folderName, pairIndex) {
      const key = this.pairDeleteKey(folderName, pairIndex);
      if (!folderName || !pairIndex || this.deletePairConfirmKey !== key || this.deletePairConfirmStep < 1 || this.pairDeletingKey) {
        return;
      }
      this.pairDeletingKey = key;
      const currentIndex = this.viewerIndex;
      const previousDetail = {
        open: this.detail.open,
        pairs: [...(this.detail.pairs || [])],
        folder: this.detail.folder ? { ...this.detail.folder } : null,
        videos: [...(this.detail.videos || [])],
      };
      const previousGallery = {
        items: [...(this.gallery.items || [])],
        total: this.gallery.total || 0,
      };
      const previousCache = this.detailCache[folderName] ? this.cloneDetailPayload(this.detailCache[folderName]) : null;
      const removedPair = (this.detail.pairs || []).find((pair) => Number(pair.pair_index) === Number(pairIndex))
        || (previousCache?.pairs || []).find((pair) => Number(pair.pair_index) === Number(pairIndex))
        || (this.gallery.items || []).find((item) => item.folder_name === folderName && Number(item.pair_index) === Number(pairIndex));
      const delta = this.pairAssetDelta(removedPair);
      const nextDetailPairs = (this.detail.pairs || []).filter((pair) => Number(pair.pair_index) !== Number(pairIndex));
      const nextSequence = (this.viewerSequence || []).filter(
        (entry) => !(entry.folder?.folder_name === folderName && Number(entry.pair?.pair_index) === Number(pairIndex)),
      );
      this.cancelDeleteViewerPair();
      if (this.detail.folder?.folder_name === folderName) {
        this.detail = {
          open: true,
          pairs: nextDetailPairs,
          folder: this.detail.folder
            ? {
                ...this.detail.folder,
                image_count: Math.max(0, (this.detail.folder.image_count || 0) - delta.images),
                livephoto_count: Math.max(0, (this.detail.folder.livephoto_count || 0) - delta.livephotos),
                asset_count: Math.max(0, (this.detail.folder.asset_count || 0) - delta.total),
              }
            : this.detail.folder,
          videos: this.detail.videos || [],
        };
        this.cacheDetailPayload(folderName, this.detail);
      }
      if (this.galleryViewMode === "pair") {
        this.removePairFromGallery(folderName, pairIndex);
      }
      if (this.detail.folder?.folder_name !== folderName) {
        this.removeCachedDetailPair(folderName, pairIndex);
      }
      if (this.viewer.open && this.viewer.folder?.folder_name === folderName && Number(this.viewer.pair?.pair_index) === Number(pairIndex)) {
        if (!nextSequence.length) {
          this.closeViewer();
        } else {
          this.viewerSequence = nextSequence;
          this.viewerIndex = Math.min(currentIndex, nextSequence.length - 1);
          this.openViewerEntry(nextSequence[this.viewerIndex], true, false);
        }
      } else if (this.viewer.open) {
        this.viewerSequence = nextSequence;
      }
      this.notify("info", "正在删除", "页面已先更新，后台正在处理删除。");
      try {
        const result = await this.api(`/api/gallery/folders/${encodeURIComponent(folderName)}/pairs/${pairIndex}/delete`, {
          method: "POST",
        });
        await Promise.all([this.refreshMeta(), this.currentView === "gallery" ? this.refreshGallery(true) : Promise.resolve()]);
        this.notify("success", "已删除", result.message);
      } catch (error) {
        this.detail = previousDetail;
        if (previousCache) {
          this.cacheDetailPayload(folderName, previousCache);
        } else {
          this.invalidateDetailCache(folderName);
        }
        this.gallery = {
          ...this.gallery,
          items: previousGallery.items,
          total: previousGallery.total,
        };
        if (!this.viewer.open) {
          const fallbackSequence = (previousDetail.pairs || []).map((pair) => ({ pair, folder: previousDetail.folder }));
          const fallbackIndex = fallbackSequence.findIndex((entry) => Number(entry.pair?.pair_index) === Number(pairIndex));
          if (fallbackIndex >= 0) {
            this.viewerSource = "detail";
            this.viewerSequence = fallbackSequence;
            this.viewerIndex = fallbackIndex;
            this.openViewerEntry(fallbackSequence[fallbackIndex], true, false);
          }
        }
        this.notify("error", "删除失败", error.message || "后台删除失败，页面内容已恢复。");
      } finally {
        if (this.pairDeletingKey === key) {
          this.pairDeletingKey = null;
        }
      }
    },

    async createSubscription() {
      const uid = String(this.newSubscriptionUid || "").trim();
      if (!uid) {
        this.notify("error", "无法添加订阅", "请输入有效的 UID。");
        return;
      }
      const previousInput = this.newSubscriptionUid;
      const tempUid = `pending-${uid}`;
      this.newSubscriptionUid = "";
      this.subscriptions = [
        {
          uid: tempUid,
          uname: `正在添加 ${uid}`,
          status: "pending",
          pull_images: true,
          image_min_count: 6,
          pull_livephoto: true,
          include_forwarded: false,
          folder_count: 0,
          image_count: 0,
          livephoto_count: 0,
        },
        ...(this.subscriptions || []),
      ];
      this.notify("info", "正在添加订阅", `已开始添加 UID ${uid}。`);
      try {
        const result = await this.api("/api/subscriptions", {
          method: "POST",
          body: JSON.stringify({ uid }),
        });
        await Promise.all([this.loadSubscriptions(), this.refreshMeta()]);
        this.notify("success", "订阅已添加", result.message);
      } catch (error) {
        this.subscriptions = (this.subscriptions || []).filter((item) => item.uid !== tempUid);
        this.newSubscriptionUid = previousInput;
        this.notify("error", "添加订阅失败", error.message || "订阅已恢复到提交前状态。");
      }
    },

    async updateSubscriptionSetting(item, field, value) {
      const allowed = ["pull_images", "image_min_count", "pull_livephoto", "include_forwarded"];
      if (!allowed.includes(field)) {
        return;
      }
      const normalizeImageThreshold = (input, fallback = 6) => {
        const parsed = Number(input);
        if (!Number.isFinite(parsed)) {
          return fallback;
        }
        return Math.max(-1, Math.min(12, parsed));
      };
      const previous = {
        pull_images: !!item.pull_images,
        image_min_count: normalizeImageThreshold(item.image_min_count, 6),
        pull_livephoto: !!item.pull_livephoto,
        include_forwarded: !!item.include_forwarded,
      };
      if (field === "image_min_count") {
        item.image_min_count = normalizeImageThreshold(value, 6);
        item.pull_images = item.image_min_count >= 0;
      } else {
        item[field] = !!value;
      }
      try {
        const result = await this.api(`/api/subscriptions/${encodeURIComponent(item.uid)}`, {
          method: "PUT",
          body: JSON.stringify({
            pull_images: item.pull_images,
            image_min_count: item.image_min_count,
            pull_livephoto: item.pull_livephoto,
            include_forwarded: item.include_forwarded,
          }),
        });
        Object.assign(item, {
          ...result.item,
          pull_images: !!result.item.pull_images,
          image_min_count: normalizeImageThreshold(result.item.image_min_count, 6),
          pull_livephoto: !!result.item.pull_livephoto,
          include_forwarded: !!result.item.include_forwarded,
        });
        this.notify("success", "订阅策略已更新", result.message);
      } catch (error) {
        Object.assign(item, previous);
      }
    },

    async refreshSubscriptionProfile(uid) {
      const target = (this.subscriptions || []).find((item) => String(item.uid) === String(uid));
      const previousName = target?.uname;
      this.replaceSubscriptionLocally(uid, (item) => ({ ...item, uname: "正在刷新昵称..." }));
      try {
        const result = await this.api(`/api/subscriptions/${encodeURIComponent(uid)}/refresh-profile`, { method: "POST" });
        const refreshed = result.item || {};
        this.subscriptions = this.subscriptions.map((item) =>
          String(item.uid) === String(uid)
            ? {
                ...item,
                ...refreshed,
                icon_url: refreshed.icon_url || refreshed.avatar_url || item.icon_url || "",
                avatar_url: refreshed.avatar_url || item.avatar_url || "",
                pull_images: !!refreshed.pull_images,
                image_min_count: Number.isFinite(Number(refreshed.image_min_count)) ? Number(refreshed.image_min_count) : 6,
                pull_livephoto: !!refreshed.pull_livephoto,
                include_forwarded: !!refreshed.include_forwarded,
              }
            : item,
        );
        await this.refreshMeta();
        this.notify("success", "昵称已刷新", result.message);
      } catch (error) {
        this.replaceSubscriptionLocally(uid, (item) => ({ ...item, uname: previousName || item.uname || item.uid }));
        this.notify("error", "刷新昵称失败", error.message || "订阅名称已恢复。");
      }
    },

    async refreshSubscriptionIcon(uid) {
      const normalized = String(uid);
      if (!normalized || this.subscriptionIconRefreshingUid === normalized) {
        return;
      }
      if (normalized.startsWith("site:")) {
        await this.refreshSiteSourceIcon({ id: normalized.replace(/^site:/, "") });
        return;
      }
      this.subscriptionIconRefreshingUid = normalized;
      this.iconLoadFailures = { ...this.iconLoadFailures, [normalized]: false };
      try {
        const result = await this.api(`/api/subscriptions/${encodeURIComponent(normalized)}/refresh-icon`, { method: "POST" });
        const refreshed = result.item || {};
        this.subscriptions = (this.subscriptions || []).map((item) =>
          String(item.uid) === normalized
            ? this.normalizeSubscriptionItem({
                ...item,
                ...refreshed,
                icon_url: Object.prototype.hasOwnProperty.call(refreshed, "avatar_url")
                  ? (refreshed.icon_url || refreshed.avatar_url || "")
                  : (refreshed.icon_url || item.icon_url || ""),
                avatar_url: Object.prototype.hasOwnProperty.call(refreshed, "avatar_url")
                  ? (refreshed.avatar_url || "")
                  : (item.avatar_url || ""),
                image_min_count: Number.isFinite(Number(refreshed.image_min_count)) ? Number(refreshed.image_min_count) : item.image_min_count,
              })
            : item,
        );
        this.notify("success", "头像已刷新", result.message || "已更新订阅头像。");
      } catch (error) {
        this.notify("error", "头像刷新失败", error.message || "请稍后重试。");
      } finally {
        this.subscriptionIconRefreshingUid = null;
      }
    },

    jumpToSubscriptionSpace(uid) {
      const target = `https://space.bilibili.com/${encodeURIComponent(uid)}/dynamic`;
      window.open(target, "_blank", "noopener,noreferrer");
    },

    askSubscriptionReload(uid) {
      const normalized = String(uid);
      if (this.subscriptionReloadConfirmUid !== normalized) {
        this.subscriptionReloadConfirmUid = normalized;
        this.subscriptionReloadConfirmStep = 1;
        return;
      }
      this.subscriptionReloadConfirmStep = 2;
    },

    cancelSubscriptionReload() {
      this.subscriptionReloadConfirmUid = null;
      this.subscriptionReloadConfirmStep = 0;
    },

    async confirmSubscriptionReload(uid) {
      if (this.subscriptionReloadConfirmUid !== String(uid) || this.subscriptionReloadConfirmStep < 2) {
        return;
      }
      this.cancelSubscriptionReload();
      this.setImmediateTaskFeedback("正在提交当前订阅的全量校验拉取任务...");
      const result = await this.api(`/api/subscriptions/${encodeURIComponent(uid)}/reload`, { method: "POST" });
      await Promise.all([this.refreshStatus(), this.refreshTasks()]);
      this.notify("info", "任务已提交", result.message);
    },

    askSubscriptionDelete(uid) {
      const normalized = String(uid);
      if (this.subscriptionDeleteConfirmUid !== normalized) {
        this.subscriptionDeleteConfirmUid = normalized;
        this.subscriptionDeleteConfirmStep = 1;
        return;
      }
      this.subscriptionDeleteConfirmStep = Math.min(this.subscriptionDeleteConfirmStep + 1, 3);
    },

    cancelSubscriptionDelete() {
      this.subscriptionDeleteConfirmUid = null;
      this.subscriptionDeleteConfirmStep = 0;
    },

    async confirmSubscriptionDelete(uid) {
      if (this.subscriptionDeleteConfirmUid !== String(uid) || this.subscriptionDeleteConfirmStep < 3) {
        return;
      }
      this.cancelSubscriptionDelete();
      const previousSubscriptions = [...(this.subscriptions || [])];
      const previousSelected = [...(this.selectedSubscriptionUids || [])];
      this.selectedSubscriptionUids = this.selectedSubscriptionUids.filter((item) => item !== String(uid));
      this.subscriptions = (this.subscriptions || []).filter((item) => String(item.uid) !== String(uid));
      this.notify("info", "正在退订", "页面已先更新，后台正在删除相关内容。");
      try {
        const result = await this.api(`/api/subscriptions/${encodeURIComponent(uid)}`, { method: "DELETE" });
        await Promise.all([this.loadSubscriptions(), this.refreshMeta(), this.refreshGallery(true), this.refreshTrash()]);
        this.notify("success", "已退订", result.message);
      } catch (error) {
        this.subscriptions = previousSubscriptions;
        this.selectedSubscriptionUids = previousSelected;
        this.notify("error", "退订失败", error.message || "订阅列表已恢复。");
      }
    },

    subscriptionReloadLabel(uid) {
      if (this.subscriptionReloadConfirmUid !== String(uid)) {
        return "全量校验拉取";
      }
      return "再次确认";
    },

    subscriptionDeleteLabel(uid) {
      if (this.subscriptionDeleteConfirmUid !== String(uid)) {
        return "退订并删除相关内容";
      }
      return this.subscriptionDeleteConfirmStep === 1 ? "再次确认" : "最后确认";
    },

    async toggleSubscriptionStatus(uid) {
      const target = (this.subscriptions || []).find((item) => String(item.uid) === String(uid));
      const previousStatus = target?.status;
      this.replaceSubscriptionLocally(uid, (item) => ({
        ...item,
        status: item.status === "paused" ? "active" : "paused",
      }));
      try {
        const result = await this.api(`/api/subscriptions/${encodeURIComponent(uid)}/toggle`, { method: "POST" });
        await this.loadSubscriptions();
        this.notify("success", "订阅状态已更新", result.message);
      } catch (error) {
        this.replaceSubscriptionLocally(uid, (item) => ({ ...item, status: previousStatus || item.status }));
        this.notify("error", "订阅状态更新失败", error.message || "订阅状态已恢复。");
      }
    },

    async toggleFavorite(item, event = null) {
      if (event) {
        event.stopPropagation();
      }
      const favorite = !item.is_favorite;
      const previous = !!item.is_favorite;
      item.is_favorite = favorite;
      if (this.detail.folder?.folder_name === item.folder_name) {
        this.detail.folder.is_favorite = favorite;
      }
      this.updateCachedDetailFavorite(item.folder_name, favorite);
      if (this.category === "favorites" && !favorite) {
        this.removeFolderFromGallery(item.folder_name);
      }
      this.refreshMeta().catch(() => {});
      try {
        const result = await this.api(`/api/gallery/folders/${encodeURIComponent(item.folder_name)}/favorite`, {
          method: "POST",
          body: JSON.stringify({ favorite }),
        });
        item.is_favorite = result.favorite;
        if (this.detail.folder?.folder_name === item.folder_name) {
          this.detail.folder.is_favorite = result.favorite;
        }
        this.updateCachedDetailFavorite(item.folder_name, result.favorite);
        await this.refreshMeta();
        this.notify("success", result.favorite ? "已收藏" : "已取消收藏", result.message);
      } catch (error) {
        item.is_favorite = previous;
        if (this.detail.folder?.folder_name === item.folder_name) {
          this.detail.folder.is_favorite = previous;
        }
        this.updateCachedDetailFavorite(item.folder_name, previous);
        await this.refreshGallery(true);
      }
    },

    cardPrimaryText(item) {
      return this.truncateCardText(item.text_prefix || item.title || item.folder_name || "");
    },

    cardSecondaryText(item) {
      return this.truncateCardText(item.title || item.folder_name || "");
    },

    truncateCardText(text) {
      const compact = String(text || "").trim();
      return compact.length > 20 ? `${compact.slice(0, 20)}…` : compact;
    },

    async approveReview(id) {
      this.reviewItems = (this.reviewItems || []).filter((item) => Number(item.id) !== Number(id));
      this.setImmediateTaskFeedback("正在提交待审核放行任务...");
      const result = await this.api(`/api/review/${id}/approve`, { method: "POST" });
      await Promise.all([this.refreshReview(), this.refreshStatus(), this.refreshMeta()]);
      this.notify("success", "已开始处理", result.message);
    },

    queuedTaskCancelLabel(task) {
      return this.queuedCancelConfirmId === Number(task.queue_id) ? "再次确认撤销" : "撤销任务";
    },

    askCancelQueuedTask(queueId) {
      const normalized = Number(queueId);
      if (!normalized) {
        return;
      }
      if (this.queuedCancelConfirmId !== normalized) {
        this.queuedCancelConfirmId = normalized;
        return;
      }
      this.confirmCancelQueuedTask(normalized);
    },

    cancelQueuedTaskPrompt() {
      this.queuedCancelConfirmId = null;
    },

    async confirmCancelQueuedTask(queueId) {
      const normalized = Number(queueId);
      if (!normalized || this.queuedCancelConfirmId !== normalized) {
        return;
      }
      const previousQueue = [...(this.queuedTasks || [])];
      this.queuedCancelConfirmId = null;
      this.queuedTasks = (this.queuedTasks || []).filter((item) => Number(item.queue_id) !== normalized);
      this.notify("info", "正在撤销排队任务", "页面已先更新，后台正在处理。");
      try {
        const result = await this.api(`/api/tasks/queue/${normalized}/cancel`, { method: "POST" });
        await Promise.all([this.refreshTasks(), this.refreshReview(), this.refreshStatus()]);
        this.notify("success", "已撤销排队任务", result.message);
      } catch (error) {
        this.queuedTasks = previousQueue;
        this.notify("error", "撤销失败", error.message || "排队任务已恢复。");
      }
    },

    canRetryTask(item) {
      return item?.status === "failed" && !!item?.details?.retry_action?.kind;
    },

    async retryTask(item) {
      if (!this.canRetryTask(item)) {
        return;
      }
      this.notify("info", "正在重试任务", `任务 #${item.id} 已开始重新提交。`);
      const result = await this.api(`/api/tasks/${item.id}/retry`, { method: "POST" });
      await Promise.all([this.refreshTasks(), this.refreshStatus(), this.refreshReview()]);
      this.notify("info", "任务已重新提交", result.message);
    },

    reviewApproveLabel(item) {
      return item?.payload?.validation_mode ? "重新拉取" : "放行下载";
    },

    async rejectReview(id) {
      const previousItems = [...(this.reviewItems || [])];
      this.reviewItems = (this.reviewItems || []).filter((item) => Number(item.id) !== Number(id));
      this.notify("info", "正在忽略", "页面已先更新，后台正在移动到垃圾桶。");
      try {
        const result = await this.api(`/api/review/${id}/reject`, { method: "POST" });
        await Promise.all([this.refreshReview(), this.refreshMeta(), this.refreshTrash()]);
        this.notify("success", "已忽略", result.message);
      } catch (error) {
        this.reviewItems = previousItems;
        this.notify("error", "忽略失败", error.message || "待审核列表已恢复。");
      }
    },

    async refreshLogs() {
      const payload = await this.api("/api/filter/logs");
      this.logs = payload.items;
      this.lazyLoaded.logs = true;
      this.sidebarCounts = { ...this.sidebarCounts, logs: this.logs.length };
    },

    clearFilterLogsButtonLabel() {
      return this.clearFilterLogsConfirmStep === 0 ? "清理已结束日志" : "再次确认清理";
    },

    askClearFilterLogs() {
      this.clearFilterLogsConfirmStep = Math.min(this.clearFilterLogsConfirmStep + 1, 1);
    },

    cancelClearFilterLogs() {
      this.clearFilterLogsConfirmStep = 0;
    },

    async confirmClearFilterLogs() {
      if (this.clearFilterLogsConfirmStep < 1) {
        return;
      }
      const previousLogs = [...(this.logs || [])];
      this.logs = [];
      this.clearFilterLogsConfirmStep = 0;
      this.notify("info", "正在清理过滤日志", "页面已先更新，后台正在处理。");
      try {
        const result = await this.api("/api/filter/logs/clear", { method: "POST" });
        await this.refreshLogs();
        this.notify("success", "过滤日志已清理", result.message);
      } catch (error) {
        this.logs = previousLogs;
        this.notify("error", "清理失败", error.message || "过滤日志已恢复。");
      }
    },

    async loadSettings() {
      const [settings, health] = await Promise.all([this.api("/api/settings"), this.api("/api/health")]);
      this.settings = settings;
      this.galleryIndexStatus = health.gallery_index || {};
      this.keywordText = (this.settings.ad_filter_keywords || []).join("\n");
      this.lazyLoaded.settings = true;
    },

    async saveSettings() {
      const { auth, ...settingsPayload } = this.settings || {};
      const payload = {
        ...settingsPayload,
        scheduler_enabled: Boolean(settingsPayload.scheduler_enabled),
        scheduler_interval_hours: Math.max(1, Number(settingsPayload.scheduler_interval_hours) || 12),
        site_scheduler_enabled: Boolean(settingsPayload.site_scheduler_enabled),
        site_scheduler_interval_hours: Math.max(1, Number(settingsPayload.site_scheduler_interval_hours) || 12),
        site_request_timeout: Math.max(30, Math.min(900, Number(settingsPayload.site_request_timeout) || 300)),
        site_request_sleep: Math.max(0, Number(settingsPayload.site_request_sleep) || 0),
        site_max_media_per_post: Math.max(1, Math.min(500, Number(settingsPayload.site_max_media_per_post) || 100)),
        site_proxy_enabled: Boolean(settingsPayload.site_proxy_enabled),
        site_proxy_host: String(settingsPayload.site_proxy_host || "127.0.0.1").trim() || "127.0.0.1",
        site_proxy_port: Math.max(1, Math.min(65535, Number(settingsPayload.site_proxy_port) || 7890)),
        review_source_open_mode: settingsPayload.review_source_open_mode === "popup" ? "popup" : "browser",
        ad_filter_keywords: this.keywordText
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean),
      };
      this.notify("info", "正在保存设置", "前端已保留当前改动，后台正在写入。");
      const savedSettings = await this.api("/api/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      this.settings = { ...savedSettings, auth: auth || this.settings.auth };
      await Promise.all([this.refreshMeta(), this.loadSettings()]);
      this.notify("success", "设置已保存", "新的拉取和过滤参数已经生效。");
    },

    validateButtonLabel() {
      return this.validateConfirmStep === 0 ? "校验当前内容" : "再次确认校验";
    },

    askValidateContent() {
      this.validateConfirmStep = Math.min(this.validateConfirmStep + 1, 2);
    },

    cancelValidateContent() {
      this.validateConfirmStep = 0;
    },

    async confirmValidateContent() {
      if (this.validateConfirmStep < 1) {
        return;
      }
      this.setImmediateTaskFeedback("正在提交内容校验任务...");
      const result = await this.api("/api/settings/validate-content", { method: "POST" });
      this.validateConfirmStep = 0;
      await this.refreshStatus();
      await this.refreshTasks();
      this.notify("info", "校验任务已提交", result.message);
    },

    rebuildIndexButtonLabel() {
      return this.rebuildIndexConfirmStep === 0 ? "重建页面索引" : "再次确认重建";
    },

    askRebuildGalleryIndex() {
      this.rebuildIndexConfirmStep = Math.min(this.rebuildIndexConfirmStep + 1, 2);
    },

    cancelRebuildGalleryIndex() {
      this.rebuildIndexConfirmStep = 0;
    },

    async confirmRebuildGalleryIndex() {
      if (this.rebuildIndexConfirmStep < 1) {
        return;
      }
      this.setImmediateTaskFeedback("正在提交页面索引重建任务...");
      const result = await this.api("/api/settings/rebuild-gallery-index", { method: "POST" });
      this.rebuildIndexConfirmStep = 0;
      await Promise.all([this.refreshStatus(), this.refreshTasks(), this.loadSettings()]);
      this.notify("info", "索引任务已提交", result.message);
    },

    resetIconsButtonLabel() {
      if (this.resetIconsRunning) {
        return "重置中";
      }
      return this.resetIconsConfirmStep === 0 ? "重置所有图标" : "再次确认重置";
    },

    askResetAllIcons() {
      if (this.resetIconsRunning) {
        return;
      }
      this.resetIconsConfirmStep = 1;
    },

    cancelResetAllIcons() {
      if (this.resetIconsRunning) {
        return;
      }
      this.resetIconsConfirmStep = 0;
    },

    async confirmResetAllIcons() {
      if (this.resetIconsConfirmStep < 1 || this.resetIconsRunning) {
        return;
      }
      this.resetIconsRunning = true;
      this.resetIconsConfirmStep = 0;
      this.notify("info", "正在重置图标", "正在重新拉取每个 UP 主头像和站点图标。");
      try {
        const result = await this.api("/api/settings/reset-icons", { method: "POST" });
        if (Array.isArray(result.items)) {
          this.subscriptions = result.items.map((item) => this.normalizeSubscriptionItem(item));
        }
        await Promise.all([
          this.loadSubscriptions(),
          this.loadSiteSources(),
          this.refreshMeta(),
          this.refreshSidebarCounts(["subscriptions", "sites"]),
        ]);
        this.iconLoadFailures = {};
        this.notify("success", "图标重置完成", result.message || "订阅图标已重新拉取。");
      } catch (error) {
        this.notify("error", "图标重置失败", error.message || "请稍后重试。");
      } finally {
        this.resetIconsRunning = false;
      }
    },

    fullReloadButtonLabel() {
      if (this.fullReloadConfirmStep === 0) {
        return "全量拉取当前所有动态";
      }
      if (this.fullReloadConfirmStep === 1) {
        return "再次确认全量拉取";
      }
      return "最后确认并开始全量拉取";
    },

    askFullReload() {
      this.fullReloadConfirmStep = Math.min(this.fullReloadConfirmStep + 1, 3);
    },

    cancelFullReload() {
      this.fullReloadConfirmStep = 0;
    },

    async confirmFullReload() {
      if (this.fullReloadConfirmStep < 3) {
        return;
      }
      this.setImmediateTaskFeedback("正在提交全量拉取任务...");
      const result = await this.api("/api/pull/reload-all", { method: "POST" });
      this.fullReloadConfirmStep = 0;
      await Promise.all([this.refreshStatus(), this.refreshTasks()]);
      this.notify("info", "已提交全量拉取", result.message);
    },

    clearDataButtonLabel() {
      if (this.clearDataConfirmStep === 0) {
        return "清空所有内容数据";
      }
      if (this.clearDataConfirmStep === 1) {
        return "再次确认清空";
      }
      return "最后确认并清空";
    },

    askClearAllData() {
      this.clearDataConfirmStep = Math.min(this.clearDataConfirmStep + 1, 3);
    },

    cancelClearAllData() {
      this.clearDataConfirmStep = 0;
    },

    async confirmClearAllData() {
      if (this.clearDataConfirmStep < 3) {
        return;
      }
      const previousState = {
        gallery: {
          ...this.gallery,
          items: [...(this.gallery.items || [])],
        },
        reviewItems: [...(this.reviewItems || [])],
        logs: [...(this.logs || [])],
        taskRuns: [...(this.taskRuns || [])],
        queuedTasks: [...(this.queuedTasks || [])],
        trashItems: [...(this.trashItems || [])],
      };
      this.clearDataConfirmStep = 0;
      this.closeViewer();
      this.closeDetail();
      this.gallery = { ...this.gallery, items: [], total: 0, page: 1 };
      this.reviewItems = [];
      this.logs = [];
      this.taskRuns = [];
      this.queuedTasks = [];
      this.trashItems = [];
      this.notify("info", "正在清空全部内容", "页面已先清空，后台正在处理。");
      try {
        const result = await this.api("/api/settings/clear-data", { method: "POST" });
        await Promise.all([
          this.refreshMeta(),
          this.refreshGallery(true),
          this.refreshReview(),
          this.refreshLogs(),
          this.refreshTasks(),
          this.refreshTrash(),
          this.refreshStatus(),
        ]);
        this.notify("success", "内容已清空", result.message);
      } catch (error) {
        this.gallery = previousState.gallery;
        this.reviewItems = previousState.reviewItems;
        this.logs = previousState.logs;
        this.taskRuns = previousState.taskRuns;
        this.queuedTasks = previousState.queuedTasks;
        this.trashItems = previousState.trashItems;
        this.notify("error", "清空失败", error.message || "页面内容已恢复。");
      }
    },

    async runPull() {
      let url = "/api/pull/run";
      if (this.currentView === "gallery" && this.selectedSubscriptionUids.length === 1) {
        url = `/api/subscriptions/${encodeURIComponent(this.selectedSubscriptionUids[0])}/pull`;
      }
      const isSitePull = this.selectedSubscriptionUids.length === 1 && String(this.selectedSubscriptionUids[0]).startsWith("site:");
      if (isSitePull) {
        this.setImmediateSiteTaskFeedback("正在提交站点拉取任务...", { running: true });
      } else {
        this.setImmediateTaskFeedback("正在提交拉取任务...");
      }
      const result = await this.api(url, { method: "POST" });
      await Promise.all([this.refreshStatus(), this.refreshTasks()]);
      this.notify("info", "任务已提交", result.message);
    },

    runPullButtonLabel() {
      if (this.currentView === "gallery" && this.selectedSubscriptionUids.length === 1) {
        return "拉取当前订阅";
      }
      return "立即拉取";
    },

    async refreshStatus() {
      const previousRunning = this.lastRunning;
      const previousTaskId = this.lastTaskId;
      const previousSiteRunning = this.lastSiteRunning;
      const previousSiteTaskId = this.lastSiteTaskId;
      const [pullStatus, health] = await Promise.all([this.api("/api/pull/status"), this.api("/api/health")]);
      this.pullStatus = pullStatus;
      this.siteStatus = health.site_status || {};
      this.siteStats = health.site_stats || {};
      this.galleryIndexStatus = health.gallery_index || this.galleryIndexStatus || {};
      const currentTaskId = this.pullStatus.last_run?.id || null;
      const currentSiteTaskId = this.siteStatus.last_run?.id || null;
      this.lastRunning = !!this.pullStatus.running;
      this.lastTaskId = currentTaskId;
      this.lastSiteRunning = !!this.siteStatus.running;
      this.lastSiteTaskId = currentSiteTaskId;
      if (currentTaskId && currentTaskId !== previousTaskId && !this.pullStatus.running) {
        await Promise.all([
          this.refreshMeta(),
          this.loadSubscriptions(),
          this.lazyLoaded.review || this.currentView === "review" ? this.refreshReview() : Promise.resolve(),
          this.lazyLoaded.logs || this.currentView === "logs" ? this.refreshLogs() : Promise.resolve(),
          this.lazyLoaded.tasks || this.currentView === "tasks" ? this.refreshTasks() : Promise.resolve(),
          this.lazyLoaded.trash || this.currentView === "trash" ? this.refreshTrash() : Promise.resolve(),
          this.lazyLoaded.sites || this.isSitePanelActive() ? this.refreshSites() : Promise.resolve(),
          this.currentView === "gallery" ? this.refreshGallery(true) : Promise.resolve(),
          this.currentView === "settings" ? this.loadSettings() : Promise.resolve(),
        ]);
      } else if (previousRunning && !this.pullStatus.running) {
        await Promise.all([
          this.refreshMeta(),
          this.loadSubscriptions(),
          this.lazyLoaded.tasks || this.currentView === "tasks" ? this.refreshTasks() : Promise.resolve(),
          this.lazyLoaded.sites || this.isSitePanelActive() ? this.refreshSites() : Promise.resolve(),
          this.currentView === "gallery" ? this.refreshGallery(true) : Promise.resolve(),
          this.currentView === "settings" ? this.loadSettings() : Promise.resolve(),
        ]);
      }
      if ((currentSiteTaskId && currentSiteTaskId !== previousSiteTaskId && !this.siteStatus.running) || (previousSiteRunning && !this.siteStatus.running)) {
        await Promise.all([
          this.refreshMeta(),
          this.loadSubscriptions(),
          this.lazyLoaded.tasks || this.currentView === "tasks" ? this.refreshTasks() : Promise.resolve(),
          this.lazyLoaded.sites || this.isSitePanelActive() ? this.refreshSites() : Promise.resolve(),
          this.currentView === "gallery" ? this.refreshGallery(true) : Promise.resolve(),
        ]);
      }
    },

    openTasks() {
      this.currentView = "tasks";
      this.closeSidebarDrawer();
      this.scrollViewTop();
      this.refreshTasks();
      this.refreshSidebarCounts(["tasks"]).catch(() => {});
    },

    openTrash() {
      this.currentView = "trash";
      this.closeSidebarDrawer();
      this.scrollViewTop();
      this.refreshTrash();
      this.refreshSidebarCounts(["trash"]).catch(() => {});
    },

    askTrashCurrentFolder() {
      this.pendingTrashFolder = this.detail.folder?.folder_name || null;
    },

    askTrashFolder(folderName) {
      this.pendingTrashFolder = folderName || null;
    },

    cancelTrashCurrentFolder() {
      this.pendingTrashFolder = null;
    },

    async trashCurrentFolder() {
      const folderName = this.detail.folder?.folder_name;
      if (!folderName || this.pendingTrashFolder !== folderName) {
        return;
      }
      const previousGalleryItems = [...(this.gallery.items || [])];
      const previousGalleryTotal = this.gallery.total || 0;
      const previousDetail = {
        open: this.detail.open,
        pairs: [...(this.detail.pairs || [])],
        folder: this.detail.folder ? { ...this.detail.folder } : null,
        videos: [...(this.detail.videos || [])],
      };
      const previousCache = this.detailCache[folderName] ? this.cloneDetailPayload(this.detailCache[folderName]) : null;
      this.pendingTrashFolder = null;
      this.closeViewer();
      this.closeDetail();
      this.removeFolderFromGallery(folderName);
      this.invalidateDetailCache(folderName);
      this.notify("info", "正在移入垃圾桶", "页面已先更新，后台正在处理删除。");
      try {
        const result = await this.api(`/api/gallery/folders/${encodeURIComponent(folderName)}/trash`, {
          method: "POST",
          body: JSON.stringify({ reason: "不喜欢" }),
        });
        await Promise.all([this.refreshMeta(), this.refreshTrash(), this.refreshTasks()]);
        this.notify("success", "已移入垃圾桶", result.message);
      } catch (error) {
        this.gallery = {
          ...this.gallery,
          items: previousGalleryItems,
          total: previousGalleryTotal,
        };
        if (!this.viewer.open && !this.detail.open && previousDetail.folder?.folder_name === folderName) {
          this.detail = previousDetail;
        }
        if (previousCache) {
          this.cacheDetailPayload(folderName, previousCache);
        }
        this.syncBodyLock();
        this.notify("error", "移入垃圾桶失败", error.message || "后端删除没有成功，内容已恢复。");
      }
    },

    async trashFolderCard(folderName) {
      if (!folderName || this.pendingTrashFolder !== folderName) {
        return;
      }
      const folder = (this.gallery.items || []).find((item) => item.folder_name === folderName);
      const previousGalleryItems = [...(this.gallery.items || [])];
      const previousGalleryTotal = this.gallery.total || 0;
      const previousCache = this.detailCache[folderName] ? this.cloneDetailPayload(this.detailCache[folderName]) : null;
      this.pendingTrashFolder = null;
      if (this.detail.folder?.folder_name === folderName) {
        this.closeDetail();
      }
      this.removeFolderFromGallery(folderName);
      this.invalidateDetailCache(folderName);
      this.notify("info", "正在移入垃圾桶", "页面已先更新，后台正在处理删除。");
      try {
        const result = await this.api(`/api/gallery/folders/${encodeURIComponent(folderName)}/trash`, {
          method: "POST",
          body: JSON.stringify({ reason: "不喜欢" }),
        });
        await Promise.all([this.refreshMeta(), this.refreshTrash(), this.refreshTasks()]);
        this.notify("success", "已移入垃圾桶", result.message);
      } catch (error) {
        this.gallery = {
          ...this.gallery,
          items: previousGalleryItems,
          total: previousGalleryTotal,
        };
        if (previousCache) {
          this.cacheDetailPayload(folderName, previousCache);
        }
        if (folder && !this.gallery.items.find((item) => item.folder_name === folderName)) {
          this.gallery = { ...this.gallery, items: [folder, ...(this.gallery.items || [])] };
        }
        this.notify("error", "移入垃圾桶失败", error.message || "后端删除没有成功，内容已恢复。");
      }
    },

    removeFolderFromGallery(folderName) {
      const nextItems = (this.gallery.items || []).filter((item) => item.folder_name !== folderName);
      const removedCount = (this.gallery.items || []).length - nextItems.length;
      if (removedCount <= 0) {
        return;
      }
      this.gallery = {
        ...this.gallery,
        items: nextItems,
        total: Math.max(0, (this.gallery.total || 0) - removedCount),
      };
    },

    removePairFromGallery(folderName, pairIndex) {
      const nextItems = (this.gallery.items || []).filter(
        (item) => !(item.folder_name === folderName && Number(item.pair_index) === Number(pairIndex)),
      );
      const removedCount = (this.gallery.items || []).length - nextItems.length;
      if (removedCount <= 0) {
        return;
      }
      this.gallery = {
        ...this.gallery,
        items: nextItems,
        total: Math.max(0, (this.gallery.total || 0) - removedCount),
      };
    },

    replaceSubscriptionLocally(uid, mapper) {
      const normalized = String(uid);
      this.subscriptions = (this.subscriptions || []).map((item) =>
        String(item.uid) === normalized ? mapper({ ...item }) : item,
      );
    },

    askRestoreTrash(itemId) {
      this.pendingRestoreTrashId = itemId;
    },

    cancelRestoreTrash() {
      this.pendingRestoreTrashId = null;
    },

    async restoreTrash(itemId, repullNow) {
      const previousTrash = [...(this.trashItems || [])];
      this.pendingRestoreTrashId = null;
      this.trashItems = (this.trashItems || []).filter((item) => Number(item.id) !== Number(itemId));
      this.notify("info", "正在恢复内容", repullNow ? "页面已先更新，后台会继续尝试立即拉取。" : "页面已先更新，后台正在恢复。");
      try {
        const result = await this.api(`/api/trash/${itemId}/restore`, {
          method: "POST",
          body: JSON.stringify({ repull_now: !!repullNow }),
        });
        await Promise.all([this.refreshTrash(), this.refreshMeta(), this.refreshGallery(true), this.refreshTasks()]);
        this.notify("success", "恢复完成", result.message);
      } catch (error) {
        this.trashItems = previousTrash;
        this.notify("error", "恢复失败", error.message || "垃圾桶列表已恢复。");
      }
    },

    async startQrLogin() {
      this.qr = await this.api("/api/auth/qr/start", { method: "POST" });
      this.notify("info", "二维码已生成", "请使用哔哩哔哩客户端扫码。");
    },

    async pollQrStatus() {
      const payload = await this.api("/api/auth/qr/status");
      this.qr = { ...this.qr, ...payload };
      if (payload.status === "scanned") {
        return;
      }
      if (payload.status === "done") {
        await this.loadSettings();
        this.qr = { status: "done", message: payload.message };
        this.notify("success", "登录成功", payload.user?.message || "账号权限已经导入到当前页面。");
        return;
      }
      if (payload.status === "expired") {
        this.notify("error", "二维码已过期", payload.message || "请重新生成二维码。");
      }
    },

    async checkAuth() {
      this.settings.auth = await this.api("/api/auth/check");
    },

    async logout() {
      await this.api("/api/auth/logout", { method: "POST" });
      this.qr = {};
      await this.loadSettings();
      this.notify("success", "已退出登录", "本地保存的 Cookie 已清除。");
    },

    async refreshSites() {
      await Promise.all([
        this.loadSiteSources(),
        this.loadSiteRules(),
        this.loadSiteLogs(),
      ]);
      this.lazyLoaded.sites = true;
    },

    async loadSiteSources() {
      const payload = await this.api("/api/site-sources");
      const nextSources = payload.items || [];
      const previousDrafts = { ...(this.siteSourceDrafts || {}) };
      const previousExpanded = { ...(this.siteSourceExpanded || {}) };
      this.siteSourceDrafts = Object.fromEntries(
        nextSources.map((source) => [
          String(source.id),
          previousDrafts[String(source.id)] || this.siteSourceDraftFromSource(source),
        ]),
      );
      this.siteSourceExpanded = Object.fromEntries(
        nextSources.map((source) => [String(source.id), !!previousExpanded[String(source.id)]]),
      );
      this.siteSources = nextSources;
      this.sidebarCounts = { ...this.sidebarCounts, sites: this.siteSources.length };
    },

    async loadSiteRules() {
      this.siteRules = await this.api("/api/site-rules");
      this.siteRules.mode = this.normalizeSiteRuleMode(this.siteRules.mode);
      const legacy = this.siteRules.keywords || [];
      const allowFallback = this.siteRules.mode === "whitelist" ? legacy : [];
      const blockFallback = this.siteRules.mode === "blacklist" ? legacy : [];
      const allowKeywords = this.uniqueLines([
        ...(this.siteRules.allow_keywords || []),
        ...(this.siteRules.title_allow || []),
        ...(this.siteRules.tag_allow || []),
        ...allowFallback,
      ]);
      const blockKeywords = this.uniqueLines([
        ...(this.siteRules.block_keywords || []),
        ...(this.siteRules.title_block || []),
        ...(this.siteRules.tag_block || []),
        ...blockFallback,
      ]);
      this.siteRuleText.allow_keywords = this.joinLines(allowKeywords);
      this.siteRuleText.block_keywords = this.joinLines(blockKeywords);
      this.siteRuleText.title_allow = "";
      this.siteRuleText.title_block = "";
      this.siteRuleText.tag_allow = "";
      this.siteRuleText.tag_block = "";
    },

    normalizeSiteRuleMode(mode) {
      return ["whitelist", "blacklist", "both"].includes(mode) ? mode : "blacklist";
    },

    siteRuleModeLabel() {
      if (this.siteRules.mode === "whitelist") return "仅白名单";
      if (this.siteRules.mode === "both") return "黑白同时";
      return "仅黑名单";
    },

    siteRuleKeywordCount(kind) {
      const key = kind === "allow" ? "allow_keywords" : "block_keywords";
      return this.splitLines(this.siteRuleText[key]).length;
    },

    async loadSiteLogs() {
      const payload = await this.api("/api/site-filter/logs");
      this.siteLogs = payload.items || [];
    },

    resetSiteSourceForm() {
      this.siteSourceForm = {
        name: "",
        slug: "",
        source_type: "html",
        entry_url: "",
        page_url_template: "",
        max_pages: 1,
        list_item_selector: "",
        detail_link_selector: "a",
        title_selector: "h1",
        date_selector: "time",
        tag_selector: ".tag",
        body_selector: "article, .content, .post-content",
        media_selector: "article img, article video, article source, .content img, .content video, .content source",
        skip_head_images: 0,
        skip_tail_images: 0,
        use_proxy: true,
        enabled: true,
        start_date: "",
        icon_url: "",
      };
      this.sitePreviewItems = [];
      this.siteSuggestion = null;
    },

    siteSourceDraftFromSource(source) {
      return {
        id: source.id,
        name: source.name || "",
        slug: source.slug || "",
        source_type: source.source_type || "html",
        entry_url: source.entry_url || "",
        page_url_template: source.page_url_template || "",
        max_pages: Number(source.max_pages || 1),
        list_item_selector: source.list_item_selector || "",
        detail_link_selector: source.detail_link_selector || "a",
        title_selector: source.title_selector || "h1",
        date_selector: source.date_selector || "time",
        tag_selector: source.tag_selector || ".tag",
        body_selector: source.body_selector || "article, .content, .post-content",
        media_selector: source.media_selector || "article img, article video, article source, .content img, .content video, .content source",
        skip_head_images: Number(source.skip_head_images || 0),
        skip_tail_images: Number(source.skip_tail_images || 0),
        use_proxy: source.use_proxy !== false && Number(source.use_proxy ?? 1) !== 0,
        enabled: Boolean(source.enabled),
        start_date: source.start_date || "",
        icon_url: source.icon_url || "",
      };
    },

    isSiteSourceExpanded(sourceId) {
      return !!this.siteSourceExpanded[String(sourceId)];
    },

    toggleSiteSourceExpanded(sourceId) {
      const key = String(sourceId);
      this.siteSourceExpanded = {
        ...this.siteSourceExpanded,
        [key]: !this.siteSourceExpanded[key],
      };
    },

    resetSiteSourceDraft(source) {
      this.siteSourceDrafts = {
        ...this.siteSourceDrafts,
        [String(source.id)]: this.siteSourceDraftFromSource(source),
      };
      this.sitePreviewItemsById = {
        ...this.sitePreviewItemsById,
        [String(source.id)]: [],
      };
    },

    siteSourceDraft(sourceId) {
      const key = String(sourceId);
      if (!this.siteSourceDrafts[key]) {
        const source = (this.siteSources || []).find((item) => String(item.id) === key);
        this.siteSourceDrafts = {
          ...this.siteSourceDrafts,
          [key]: source ? this.siteSourceDraftFromSource(source) : {},
        };
      }
      return this.siteSourceDrafts[key];
    },

    siteSourceDraftValue(sourceId, field) {
      const draft = this.siteSourceDraft(sourceId);
      if (field === "enabled" || field === "use_proxy") {
        return field === "enabled" ? !!draft.enabled : draft.use_proxy !== false;
      }
      return draft[field] ?? "";
    },

    updateSiteSourceDraft(sourceId, field, value) {
      const key = String(sourceId);
      const numericFields = new Set(["max_pages", "skip_head_images", "skip_tail_images"]);
      const draft = this.siteSourceDraft(sourceId);
      let nextValue = value;
      if (numericFields.has(field)) {
        const fallback = field === "max_pages" ? 1 : 0;
        nextValue = Math.max(fallback, Number(value) || fallback);
      }
      if (field === "enabled" || field === "use_proxy") {
        nextValue = !!value;
      }
      this.siteSourceDrafts = {
        ...this.siteSourceDrafts,
        [key]: {
          ...draft,
          [field]: nextValue,
        },
      };
    },

    siteSourceStatusText(source) {
      return source.enabled ? "启用" : "停用";
    },

    siteSourceCountText(source) {
      return `贴文 ${source.post_count || 0} · 媒体 ${source.asset_count || 0}`;
    },

    siteSourceProxyText(source) {
      return source.use_proxy === false || Number(source.use_proxy ?? 1) === 0 ? "不使用站点代理" : "应用站点代理";
    },

    siteSourceSavingLabel(sourceId) {
      return this.siteSourceSavingById[String(sourceId)] ? "保存中" : "保存设置";
    },

    siteSourceTestingLabel(sourceId) {
      return this.siteTestLoadingById[String(sourceId)] ? "解析中" : "测试解析";
    },

    async saveSiteSource(sourceId = null) {
      const key = sourceId == null ? null : String(sourceId);
      if (key && this.siteSourceSavingById[key]) return;
      if (!key && this.siteSourceSaving) return;
      const draft = key ? this.siteSourceDraft(sourceId) : this.siteSourceForm;
      if (!draft?.entry_url) {
        this.notify("error", "保存失败", "请输入入口 URL。");
        return;
      }
      const body = JSON.stringify(draft);
      const url = draft.id
        ? `/api/site-sources/${encodeURIComponent(draft.id)}`
        : "/api/site-sources";
      const method = draft.id ? "PUT" : "POST";
      if (key) {
        this.siteSourceSavingById = { ...this.siteSourceSavingById, [key]: true };
      } else {
        this.siteSourceSaving = true;
      }
      this.notify("info", "正在保存站点设置", draft.name || "新站点来源");
      try {
        const result = await this.api(url, { method, body });
        this.notify("success", "站点来源已保存", result.message || "来源配置已更新。");
        if (key && result.item) {
          this.siteSourceDrafts = {
            ...this.siteSourceDrafts,
            [key]: this.siteSourceDraftFromSource(result.item),
          };
        }
        if (!key) {
          this.resetSiteSourceForm();
          this.newSiteSourceExpanded = false;
        }
        await Promise.all([this.loadSiteSources(), this.refreshStatus()]);
      } finally {
        if (key) {
          this.siteSourceSavingById = { ...this.siteSourceSavingById, [key]: false };
        } else {
          this.siteSourceSaving = false;
        }
      }
    },

    async deleteSiteSource(source) {
      const confirmed = window.confirm(`删除站点来源：${source.name}`);
      if (!confirmed) return;
      const result = await this.api(`/api/site-sources/${encodeURIComponent(source.id)}`, { method: "DELETE" });
      this.notify("success", "站点来源已删除", result.message || "来源已删除。");
      await Promise.all([this.loadSiteSources(), this.refreshStatus()]);
    },

    async refreshSiteSourceIcon(source) {
      const sourceId = Number(source?.id);
      if (!sourceId || this.siteIconRefreshingById[String(sourceId)]) {
        return;
      }
      const key = String(sourceId);
      this.siteIconRefreshingById = { ...this.siteIconRefreshingById, [key]: true };
      this.iconLoadFailures = { ...this.iconLoadFailures, [`site:${sourceId}`]: false };
      this.notify("info", "正在刷新站点图标", "正在重新探测并缓存站点 icon。");
      try {
        const result = await this.api(`/api/site-sources/${encodeURIComponent(sourceId)}/refresh-icon`, { method: "POST" });
        if (result.item) {
          this.siteSources = (this.siteSources || []).map((item) =>
            Number(item.id) === sourceId ? { ...item, ...result.item } : item,
          );
          this.siteSourceDrafts = {
            ...this.siteSourceDrafts,
            [key]: this.siteSourceDraftFromSource(result.item),
          };
          this.subscriptions = (this.subscriptions || []).map((item) =>
            String(item.uid) === `site:${sourceId}`
              ? this.normalizeSubscriptionItem({ ...item, icon_url: result.item.icon_url || "", updated_at: result.item.updated_at || item.updated_at })
              : item,
          );
          this.iconLoadFailures = { ...this.iconLoadFailures, [`site:${sourceId}`]: false };
        }
        this.notify("success", "站点图标已刷新", result.message || "已更新站点图标。");
      } catch (error) {
        this.notify("error", "站点图标刷新失败", error.message || "请稍后重试。");
      } finally {
        this.siteIconRefreshingById = { ...this.siteIconRefreshingById, [key]: false };
      }
    },

    askSiteValidate(sourceId) {
      const normalized = Number(sourceId);
      if (this.siteValidateConfirmId !== normalized) {
        this.siteValidateConfirmId = normalized;
        this.siteValidateConfirmStep = 1;
        return;
      }
      this.siteValidateConfirmStep = 2;
    },

    cancelSiteValidate() {
      this.siteValidateConfirmId = null;
      this.siteValidateConfirmStep = 0;
    },

    siteValidateLabel(sourceId) {
      if (this.siteValidateConfirmId !== Number(sourceId)) {
        return "全量校验";
      }
      return "再次确认校验";
    },

    askSiteClearDelete(sourceId) {
      const normalized = Number(sourceId);
      if (this.siteClearDeleteConfirmId !== normalized) {
        this.siteClearDeleteConfirmId = normalized;
        this.siteClearDeleteConfirmStep = 1;
        return;
      }
      this.siteClearDeleteConfirmStep = Math.min(this.siteClearDeleteConfirmStep + 1, 3);
    },

    cancelSiteClearDelete() {
      this.siteClearDeleteConfirmId = null;
      this.siteClearDeleteConfirmStep = 0;
    },

    siteClearDeleteLabel(sourceId) {
      if (this.siteClearDeleteConfirmId !== Number(sourceId)) {
        return "清空并删除";
      }
      if (this.siteClearDeleteConfirmStep === 1) {
        return "再次确认";
      }
      return "最后确认";
    },

    async confirmSiteClearDelete(sourceId) {
      if (this.siteClearDeleteConfirmId !== Number(sourceId) || this.siteClearDeleteConfirmStep < 3) {
        return;
      }
      this.cancelSiteClearDelete();
      const result = await this.api(`/api/site-sources/${encodeURIComponent(sourceId)}/clear-delete`, { method: "POST" });
      this.notify("success", "站点已清空并删除", result.message || "站点内容已移除。");
      await Promise.all([
        this.refreshSites(),
        this.refreshMeta(),
        this.loadSubscriptions(),
        this.refreshGallery(true),
        this.refreshStatus(),
      ]);
    },

    async testSiteSource(sourceId = null) {
      const key = sourceId == null ? null : String(sourceId);
      if (key && this.siteTestLoadingById[key]) return;
      if (!key && this.siteTestLoading) return;
      const draft = key ? this.siteSourceDraft(sourceId) : this.siteSourceForm;
      if (key) {
        this.siteTestLoadingById = { ...this.siteTestLoadingById, [key]: true };
        this.sitePreviewItemsById = { ...this.sitePreviewItemsById, [key]: [] };
      } else {
        this.siteTestLoading = true;
        this.sitePreviewItems = [];
      }
      try {
        const payload = await this.api("/api/site-sources/test", {
          method: "POST",
          body: JSON.stringify(draft),
        });
        if (key) {
          this.sitePreviewItemsById = { ...this.sitePreviewItemsById, [key]: payload.items || [] };
        } else {
          this.sitePreviewItems = payload.items || [];
        }
        this.notify("success", "解析完成", `解析到 ${(payload.items || []).length} 条预览。`);
      } finally {
        if (key) {
          this.siteTestLoadingById = { ...this.siteTestLoadingById, [key]: false };
        } else {
          this.siteTestLoading = false;
        }
      }
    },

    async suggestSiteSource() {
      if (this.siteSuggestLoading) return;
      const entryUrl = String(this.siteSourceForm.entry_url || "").trim();
      if (!entryUrl) {
        this.notify("error", "自动填写失败", "请输入入口 URL。");
        return;
      }
      this.siteSuggestLoading = true;
      this.siteSuggestion = null;
      try {
        const payload = await this.api("/api/site-sources/suggest", {
          method: "POST",
          body: JSON.stringify({ entry_url: entryUrl }),
        });
        const suggestion = payload.suggestion || {};
        this.siteSourceForm = this.applySiteSourceSuggestion(this.siteSourceForm, suggestion);
        this.sitePreviewItems = suggestion.preview || [];
        this.siteSuggestion = suggestion;
        this.notify("success", "自动填写完成", suggestion.message || "已生成站点解析参数。");
      } finally {
        this.siteSuggestLoading = false;
      }
    },

    applySiteSourceSuggestion(form, suggestion) {
      const next = { ...form };
      const fields = [
        "source_type",
        "entry_url",
        "page_url_template",
        "max_pages",
        "list_item_selector",
        "detail_link_selector",
        "title_selector",
        "date_selector",
        "tag_selector",
        "body_selector",
        "media_selector",
        "skip_head_images",
        "skip_tail_images",
        "use_proxy",
        "icon_url",
        "enabled",
        "start_date",
      ];
      for (const field of fields) {
        if (suggestion[field] !== undefined && suggestion[field] !== null) {
          next[field] = suggestion[field];
        }
      }
      for (const field of ["name", "slug"]) {
        if (!String(next[field] || "").trim() && suggestion[field]) {
          next[field] = suggestion[field];
        }
      }
      return next;
    },

    async syncSiteSource(source) {
      this.setImmediateSiteTaskFeedback(`正在提交 ${source.name || "站点"} 同步任务...`, { running: true });
      const result = await this.api(`/api/site-sources/${encodeURIComponent(source.id)}/sync`, { method: "POST" });
      this.notify("info", "站点同步已提交", result.message || "已开始同步。");
      await Promise.all([this.refreshStatus(), this.refreshTasks()]);
    },

    async validateSiteSource(source) {
      if (this.siteValidateConfirmId !== Number(source.id) || this.siteValidateConfirmStep < 2) {
        return;
      }
      this.cancelSiteValidate();
      this.setImmediateSiteTaskFeedback(`正在提交 ${source.name || "站点"} 全量校验任务...`, { running: true });
      const result = await this.api(`/api/site-sources/${encodeURIComponent(source.id)}/validate`, { method: "POST" });
      this.notify("info", "站点全量校验已提交", result.message || "已开始全量校验。");
      await Promise.all([this.refreshStatus(), this.refreshTasks()]);
    },

    async pullSiteSubscription(item) {
      this.setImmediateSiteTaskFeedback(`正在提交 ${item.uname || "站点"} 拉取任务...`, { running: true });
      const result = await this.api(`/api/subscriptions/${encodeURIComponent(item.uid)}/pull`, { method: "POST" });
      this.notify("info", "站点拉取已提交", result.message || "已开始拉取当前站点。");
      await Promise.all([this.refreshStatus(), this.refreshTasks()]);
    },

    async syncAllSites() {
      this.setImmediateSiteTaskFeedback("正在提交全部站点同步任务...", { running: true });
      const result = await this.api("/api/site-sync", { method: "POST" });
      this.notify("info", "站点同步已提交", result.message || "已开始同步。");
      await Promise.all([this.refreshStatus(), this.refreshTasks()]);
    },

    async exportSiteSources() {
      const payload = await this.api("/api/site-sources/export");
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "site-sources.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      this.notify("success", "来源配置已导出", "站点来源 JSON 已生成。");
    },

    async importSiteSources(event) {
      const file = event.target.files && event.target.files[0];
      event.target.value = "";
      if (!file) return;
      const payload = JSON.parse(await file.text());
      const result = await this.api("/api/site-sources/import", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await Promise.all([this.loadSiteSources(), this.refreshStatus()]);
      this.notify("success", "导入完成", `新增 ${result.created || 0}，更新 ${result.updated || 0}。`);
    },

    async saveSiteRules() {
      const allowKeywords = this.splitLines(this.siteRuleText.allow_keywords);
      const blockKeywords = this.splitLines(this.siteRuleText.block_keywords);
      const payload = {
        mode: this.normalizeSiteRuleMode(this.siteRules.mode),
        keywords: [],
        allow_keywords: allowKeywords,
        block_keywords: blockKeywords,
        title_allow: [],
        title_block: [],
        tag_allow: [],
        tag_block: [],
        use_regex: Boolean(this.siteRules.use_regex),
      };
      this.siteRules = await this.api("/api/site-rules", { method: "PUT", body: JSON.stringify(payload) });
      this.siteRules.mode = this.normalizeSiteRuleMode(this.siteRules.mode);
      this.notify("success", "站点规则已保存", "后续同步会使用新的过滤规则。");
    },

    async clearSiteLogs() {
      if (!this.siteLogsClearConfirm) {
        this.siteLogsClearConfirm = true;
        return;
      }
      this.siteLogsClearConfirm = false;
      const result = await this.api("/api/site-filter/logs/clear", { method: "POST" });
      this.siteLogs = [];
      await this.refreshStatus();
      this.notify("success", "站点过滤日志已清空", result.message || "历史记录已清理。");
    },

    cancelClearSiteLogs() {
      this.siteLogsClearConfirm = false;
    },

    joinLines(items) {
      return (items || []).join("\n");
    },

    uniqueLines(items) {
      const seen = new Set();
      const output = [];
      for (const item of items || []) {
        const value = String(item || "").trim();
        if (!value || seen.has(value)) continue;
        seen.add(value);
        output.push(value);
      }
      return output;
    },

    splitLines(text) {
      return String(text || "")
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean);
    },
  };
}
