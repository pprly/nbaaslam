// NBA Value Analyzer v2 - Frontend JavaScript

// State
let state = {
    games: [],
    players: [],
    valueBets: [],
    filters: {
        search: '',
        team: '',
        lineMin: 10,
        lineMax: 40,
        stability: 'all',
        sortBy: 'edge'
    }
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeFilters();
    initializeTabs();
    
    // Auto-load demo data
    loadDemoData();
});

// ========== FILTERS ==========

function initializeFilters() {
    // Search
    document.getElementById('playerSearch').addEventListener('input', (e) => {
        state.filters.search = e.target.value.toLowerCase();
        applyFilters();
    });
    
    // Team filter
    document.getElementById('teamFilter').addEventListener('change', (e) => {
        state.filters.team = e.target.value;
        applyFilters();
    });
    
    // Line range
    const lineMin = document.getElementById('lineMin');
    const lineMax = document.getElementById('lineMax');
    
    lineMin.addEventListener('input', (e) => {
        state.filters.lineMin = parseFloat(e.target.value);
        document.getElementById('lineMinVal').textContent = e.target.value;
        applyFilters();
    });
    
    lineMax.addEventListener('input', (e) => {
        state.filters.lineMax = parseFloat(e.target.value);
        document.getElementById('lineMaxVal').textContent = e.target.value;
        applyFilters();
    });
    
    // Stability toggle
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            state.filters.stability = e.target.dataset.stability;
            applyFilters();
        });
    });
    
    // Sort
    document.getElementById('sortBy').addEventListener('change', (e) => {
        state.filters.sortBy = e.target.value;
        applyFilters();
    });
}

function applyFilters() {
    let filtered = [...state.players];
    
    // Search
    if (state.filters.search) {
        filtered = filtered.filter(p => 
            p.name.toLowerCase().includes(state.filters.search)
        );
    }
    
    // Team
    if (state.filters.team) {
        filtered = filtered.filter(p => p.team === state.filters.team);
    }
    
    // Line range
    filtered = filtered.filter(p => 
        p.line >= state.filters.lineMin && p.line <= state.filters.lineMax
    );
    
    // Stability
    if (state.filters.stability !== 'all') {
        filtered = filtered.filter(p => {
            if (state.filters.stability === 'high') {
                return p.stability_score >= 70;
            } else {
                return p.stability_score < 50;
            }
        });
    }
    
    // Sort
    filtered.sort((a, b) => {
        switch (state.filters.sortBy) {
            case 'edge':
                return (b.edge || 0) - (a.edge || 0);
            case 'stability':
                return b.stability_score - a.stability_score;
            case 'line':
                return b.line - a.line;
            case 'name':
                return a.name.localeCompare(b.name);
            default:
                return 0;
        }
    });
    
    renderPlayers(filtered);
}

// ========== TABS ==========

function initializeTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            const tabName = e.target.dataset.tab;
            
            // Update tab buttons
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            e.target.classList.add('active');
            
            // Update content
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.getElementById(`tab-${tabName}`).classList.add('active');
        });
    });
}

// ========== DATA LOADING ==========

async function loadDemoData() {
    showLoading();
    
    try {
        const response = await fetch('/api/demo');
        const data = await response.json();
        
        if (data.success) {
            updateState(data);
            showSuccess('✓ Демо данные загружены');
        } else {
            showError('Ошибка: ' + data.error);
        }
    } catch (error) {
        showError('Ошибка загрузки: ' + error);
    }
}

async function loadLiveData() {
    showLoading();
    
    try {
        const response = await fetch('/api/live');
        const data = await response.json();
        
        if (data.success) {
            updateState(data);
            showSuccess('✓ Live данные загружены');
        } else {
            showError(data.error);
        }
    } catch (error) {
        showError('Ошибка: ' + error);
    }
}

async function refreshData() {
    // Используем кешированные данные если есть
    const lastMode = localStorage.getItem('lastMode') || 'demo';
    
    if (lastMode === 'live') {
        await loadLiveData();
    } else {
        await loadDemoData();
    }
}

function updateState(data) {
    state.games = data.games || [];
    state.players = data.players || [];
    state.valueBets = data.value_bets || [];
    
    // Update stats
    updateStats();
    
    // Update team filter
    updateTeamFilter();
    
    // Render all
    renderGames();
    renderPlayers(state.players);
    renderValueBets();
    
    // Save mode
    localStorage.setItem('lastMode', data.mode || 'demo');
}

function updateStats() {
    document.getElementById('statGames').textContent = state.games.length;
    document.getElementById('statPlayers').textContent = state.players.length;
    document.getElementById('statValueBets').textContent = state.valueBets.length;
    
    const avgEdge = state.valueBets.length > 0
        ? (state.valueBets.reduce((sum, vb) => sum + vb.edge, 0) / state.valueBets.length).toFixed(1)
        : 0;
    document.getElementById('statAvgEdge').textContent = avgEdge + '%';
}

function updateTeamFilter() {
    const teams = [...new Set(state.players.map(p => p.team))].sort();
    const select = document.getElementById('teamFilter');
    
    select.innerHTML = '<option value="">Все команды</option>';
    teams.forEach(team => {
        const option = document.createElement('option');
        option.value = team;
        option.textContent = team;
        select.appendChild(option);
    });
}

// ========== RENDERING ==========

function renderGames() {
    const container = document.getElementById('gamesGrid');
    
    if (state.games.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>Нет матчей на сегодня</p></div>';
        return;
    }
    
    container.innerHTML = state.games.map(game => `
        <div class="game-card" onclick="selectGame('${game.id}')">
            <div class="game-header">
                <span class="game-time">${formatGameTime(game.time)}</span>
                ${game.live ? '<span class="game-live">● LIVE</span>' : ''}
            </div>
            
            <div class="teams">
                <div class="team">
                    <div>
                        <div class="team-name">${game.away_team}</div>
                        <div class="team-abbr">${game.away_abbr}</div>
                    </div>
                </div>
                <div style="text-align: center; color: var(--text-secondary); margin: 8px 0;">@</div>
                <div class="team">
                    <div>
                        <div class="team-name">${game.home_team}</div>
                        <div class="team-abbr">${game.home_abbr}</div>
                    </div>
                </div>
            </div>
            
            ${renderGamePlayers(game.players)}
        </div>
    `).join('');
}

function renderGamePlayers(players) {
    if (!players || players.length === 0) {
        return '';
    }
    
    return `
        <div class="players-preview">
            ${players.slice(0, 4).map(p => `
                <span class="player-chip">${p}</span>
            `).join('')}
            ${players.length > 4 ? `<span class="player-chip">+${players.length - 4}</span>` : ''}
        </div>
    `;
}

function renderPlayers(players) {
    const container = document.getElementById('playersTable');
    
    if (players.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>Нет игроков</p></div>';
        return;
    }
    
    container.innerHTML = `
        <table class="players-table">
            <thead>
                <tr>
                    <th>Игрок</th>
                    <th>Линия</th>
                    <th>Avg L10</th>
                    <th>STD</th>
                    <th>Hit%</th>
                    <th>Stability</th>
                    <th>Edge</th>
                </tr>
            </thead>
            <tbody>
                ${players.map(p => `
                    <tr onclick="selectPlayer('${p.name}')">
                        <td class="player-name-cell">
                            <div>${p.name}</div>
                            <div class="player-team">${p.team} vs ${p.opponent}</div>
                        </td>
                        <td><strong>${p.line}</strong></td>
                        <td>${p.avg_last_10}</td>
                        <td>${p.std}</td>
                        <td>${p.hit_rate}%</td>
                        <td>
                            <span class="badge ${getStabilityBadge(p.stability_score)}">
                                ${p.stability_score}
                            </span>
                        </td>
                        <td>
                            ${p.edge ? `<strong style="color: var(--accent-primary)">+${p.edge}%</strong>` : '-'}
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function renderValueBets() {
    const container = document.getElementById('valueBetsList');
    const countBadge = document.getElementById('valueBetsCount');
    
    countBadge.textContent = state.valueBets.length;
    
    if (state.valueBets.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>Value bets не найдены</p></div>';
        return;
    }
    
    container.innerHTML = state.valueBets.map(vb => `
        <div class="value-bet-item ${vb.bet_type.toLowerCase()}" onclick="selectPlayer('${vb.player}')">
            <div class="vb-header">
                <div class="vb-player">${vb.player}</div>
                <div class="vb-edge">+${vb.edge}%</div>
            </div>
            
            <div class="vb-details">
                <div class="vb-detail">
                    ${vb.bet_type} <span>${vb.line}</span>
                </div>
                <div class="vb-detail">
                    Model: <span>${vb.model_prob}%</span>
                </div>
                <div class="vb-detail">
                    Conf: <span>${vb.confidence}%</span>
                </div>
            </div>
        </div>
    `).join('');
}

// ========== HELPERS ==========

function formatGameTime(timeStr) {
    const date = new Date(timeStr);
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
}

function getStabilityBadge(score) {
    if (score >= 70) return 'badge-success';
    if (score >= 50) return 'badge-warning';
    return 'badge-danger';
}

function selectGame(gameId) {
    console.log('Selected game:', gameId);
    // TODO: Show game details
}

function selectPlayer(playerName) {
    console.log('Selected player:', playerName);
    // TODO: Show player details modal
}

function showLoading() {
    document.getElementById('gamesGrid').innerHTML = '<div class="loading"><div class="spinner"></div><p>Загрузка...</p></div>';
    document.getElementById('playersTable').innerHTML = '<div class="loading"><div class="spinner"></div><p>Загрузка...</p></div>';
}

function showSuccess(message) {
    // TODO: Implement toast notifications
    console.log('✓', message);
}

function showError(message) {
    // TODO: Implement toast notifications
    console.error('✗', message);
    alert(message);
}
