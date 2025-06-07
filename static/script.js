let chart;
let trendChart;

function debounce(fn, delay = 50) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

function fetchAndRender({ skipTable = false } = {}) {
  const measure = document.getElementById('measureSelect').value;
   // ✅ Set the title above both charts
   document.getElementById('selectedMeasureTitle').textContent = measure || '';
  const region = document.getElementById('regionSelect').value;

  const params = new URLSearchParams();
  params.append('measure', measure);
  
  if (region) {
    params.append('regions[]', region);
  }

  fetch(`/pareto-data?${params.toString()}`)
    .then(res => res.json())
    .then(data => {
      data.sort((a, b) => b['Measure_Value'] - a['Measure_Value']);

      const labels = data.map(d => d['Geographical Description']);
      const values = data.map(d => d['Measure_Value']);

      const highlightSelect = document.getElementById('highlightSelect');
      const previousValue = highlightSelect.tomselect
        ? highlightSelect.tomselect.getValue()
        : highlightSelect.value;

      if (highlightSelect.tomselect) {
        highlightSelect.tomselect.destroy();
      }

      highlightSelect.innerHTML = '<option value="">None</option>';
      const names = Array.from(new Set(data.map(d => d['Geographical Description'])))
        .sort((a, b) => a.localeCompare(b));

      data.forEach(row => {
        const option = document.createElement('option');
        option.value = row['Geographical Description'];
        option.textContent = row['Geographical Description'];
        option.setAttribute('data-region', row['Council region'] || '');
        highlightSelect.appendChild(option);
      });

      new TomSelect('#highlightSelect', {
        create: false,
        sortField: { field: 'text', direction: 'asc' },
        placeholder: 'Select a local authority...'
      });

      if (names.includes(previousValue) && highlightSelect.tomselect) {
        highlightSelect.tomselect.setValue(previousValue, true);
      }

      const selectedHighlight = highlightSelect.tomselect
        ? highlightSelect.tomselect.getValue()
        : '';

      const backgroundColors = labels.map(label =>
        label === selectedHighlight ? 'rgba(255, 99, 132, 0.8)' : 'rgba(54, 162, 235, 0.6)'
      );

      const ctx = document.getElementById('paretoChart').getContext('2d');
      if (chart) chart.destroy();

      chart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: 'Measure Value',
            data: values,
            backgroundColor: backgroundColors
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            tooltip: { enabled: true },
            legend: { display: false },
            title: {
              display: false,
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              title: { display: true, text: 'Value' }
            },
            x: {
              title: { display: true, text: 'Council' }
            }
          }
        }
      });

      if (!skipTable) {
        updateLATable(selectedHighlight || '');
      }
      fetchTrendData();  // also update trend graph
      populateCostFilterOptions();
    });
}

function updateDisaggregationOptions(measure) {
  fetch(`/disaggregation-options?measure=${encodeURIComponent(measure)}`)
    .then(res => res.json())
    .then(options => {
      const disaggSelect = document.getElementById('disaggSelect');
      disaggSelect.innerHTML = '';

      if (options && options.length > 0) {
        disaggSelect.disabled = false;
        disaggSelect.classList.remove('bg-gray-100', 'text-gray-400');
        disaggSelect.classList.add('bg-white');

        const placeholderOption = document.createElement('option');
        placeholderOption.value = '';
        placeholderOption.textContent = 'Select demographic';
        disaggSelect.appendChild(placeholderOption);

        options.forEach(opt => {
          const option = document.createElement('option');
          option.value = opt;
          option.textContent = opt;
          disaggSelect.appendChild(option);
        });

        disaggSelect.value = options.includes('Total') ? 'Total' : '';
      } else {
        disaggSelect.disabled = true;
        disaggSelect.classList.remove('bg-white');
        disaggSelect.classList.add('bg-gray-100', 'text-gray-400');

        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No disaggregation for this measure';
        disaggSelect.appendChild(option);
        disaggSelect.value = '';
      }

      fetchAndRender();
    });
}

function generateSummary() {
  const council = document.getElementById('councilSelect').value;

  fetch(`/mistral-summary?council=${encodeURIComponent(council)}`)
    .then(res => res.json())
    .then(data => {
      const output = document.getElementById('mistralSummary');
      output.innerText = data.summary || 'No summary available.';
    });
}

function fetchTrendData() {
  const measure = document.getElementById('measureSelect').value;
  const la = document.getElementById('highlightSelect').tomselect?.getValue() || '';

  const params = new URLSearchParams();
  params.append('measure', measure);
  if (la) params.append('la', la);

  fetch(`/trend-data?${params.toString()}`)
    .then(res => res.json())
    .then(data => {
      const ctx = document.getElementById('trendChart').getContext('2d');
      if (trendChart) trendChart.destroy();

      const buildSeries = (label, entries, color) => ({
        label,
        data: entries.map(d => ({ x: d.Year, y: d.Measure_Value })),
        borderColor: color,
        backgroundColor: color,
        tension: 0.3,
        spanGaps: true
      });

      const datasets = [];

      if (data.england) datasets.push(buildSeries('England', data.england, 'rgba(54, 162, 235, 0.2)'));
      if (data.region) {
       const regionName = data.region.length > 0 ? data.region[0].Region || 'Region' : 'Region';
       datasets.push(buildSeries(regionName, data.region, 'rgba(54, 162, 235, 0.4)'));
      }
      if (data.la) {
       const laName = document.getElementById('highlightSelect').tomselect?.getItem()?.innerText || la;
       datasets.push(buildSeries(laName, data.la, 'rgba(255, 99, 132, 1)'));
      }

      // Dynamically collect all unique years across all series
      const allYears = new Set();
      [...(data.england || []), ...(data.region || []), ...(data.la || [])].forEach(d => {
        allYears.add(d.Year);
      });
      const sortedYears = Array.from(allYears).sort();

      trendChart = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
          responsive: true,
          plugins: {
            title: {
              display: false,
            },
            tooltip: { mode: 'index', intersect: false },
            legend: { display: true }
          },
          interaction: { mode: 'nearest', axis: 'x', intersect: false },
          scales: {
            x: {
              type: 'category',
              labels: sortedYears,
              offset: true,  // ✅ add spacing before first label
              title: { display: true, text: 'Year' }
            },
            y: {
              title: { display: true, text: 'Value' },
              ticks: { precision: 1 },
              beginAtZero: false,
              suggestedMin: (ctx) => {
                const values = ctx.chart.data.datasets.flatMap(d => d.data.map(p => p.y));
                const min = Math.min(...values);
                const range = Math.max(...values) - min;
                return min - range * 0.05;
              },
              suggestedMax: (ctx) => {
                const values = ctx.chart.data.datasets.flatMap(d => d.data.map(p => p.y));
                const max = Math.max(...values);
                const range = max - Math.min(...values);
                return max + range * 0.05;
              }
            }
          }
        }
      });
    });
}

function updateLATable(selectedLA) {
  const loading = document.getElementById('benchmarkingLoading');
  const container = document.getElementById('laMeasuresTable');

  if (selectedLA) {
    loading.classList.remove('hidden');
    container.classList.add('hidden');
  }
  const params = new URLSearchParams();
  if (selectedLA) params.append('la', selectedLA);

  fetch(`/la-outcomes?${params.toString()}`)
    .then(res => res.json())
    .then(data => {
      if (!data.length) {
        container.innerHTML = '<p class="text-gray-600 text-sm">Select a local authority to see benchmarking detail.</p>';
        loading.classList.add('hidden');
        container.classList.remove('hidden');
        return;
      }

      const rows = data
        .filter(row => row['Disaggregation Level'] === 'Total')
        .map(row => {
          const isProportion = row['Measure Group Description']?.toLowerCase().startsWith('proportion');
          const value = parseFloat(row['Measure_Value']);
          const formattedValue = isProportion ? `${Math.round(value)}%` : value.toFixed(2);

          const percentile = Math.round(row['Percentile_National']) || 0;
          const direction = row['Direction']?.toLowerCase();
          const normalised = direction === 'lower is better' ? 100 - percentile : percentile;

          const RED = '#ed7979', AMBER = '#ffca6e', GREEN = '#78c474';
          const interpolateColor = (c1, c2, f) => {
            const hex = x => parseInt(x, 16);
            const rgb = c => [hex(c.slice(1,3)), hex(c.slice(3,5)), hex(c.slice(5,7))];
            const [r1, g1, b1] = rgb(c1), [r2, g2, b2] = rgb(c2);
            const r = Math.round(r1 + (r2 - r1) * f);
            const g = Math.round(g1 + (g2 - g1) * f);
            const b = Math.round(b1 + (b2 - b1) * f);
            return `rgb(${r}, ${g}, ${b})`;
          };

          const color = normalised < 50
            ? interpolateColor(RED, AMBER, normalised / 50)
            : interpolateColor(AMBER, GREEN, (normalised - 50) / 50);

          const formatOrdinal = n => {
            const s = ["th", "st", "nd", "rd"];
            const v = n % 100;
            return n + (s[(v - 20) % 10] || s[v] || s[0]);
          };

          return `
            <tr class="border-b">
              <td class="px-4 py-2 text-sm">${row['Measure Group']}</td>
              <td class="px-4 py-2 text-sm">${row['Measure Group Description']}</td>
              <td class="px-4 py-2 text-sm">${formattedValue}</td>
              <td class="px-4 py-2 text-sm" style="background-color: ${color};">${formatOrdinal(percentile)}</td>
            </tr>
          `;
        }).join('');

      container.innerHTML = `
        <table class="min-w-full text-left border rounded mt-6">
          <thead class="bg-gray-100">
            <tr>
              <th class="px-4 py-2 text-sm font-medium">ASCOF Measure</th>
              <th class="px-4 py-2 text-sm font-medium">Description</th>
              <th class="px-4 py-2 text-sm font-medium">Value</th>
              <th class="px-4 py-2 text-sm font-medium">National Percentile</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;

      loading.classList.add('hidden');
      container.classList.remove('hidden');
    });
}

// Event listeners
document.getElementById('measureSelect').addEventListener('change', function () {
  updateDisaggregationOptions(this.value);
  fetchAndRender({ skipTable: true });  // ❌ don’t reload table
});

document.getElementById('regionSelect').addEventListener('change', function () {
  fetchAndRender({ skipTable: true });  // ❌ don’t reload table
});

document.getElementById('regionSelect').addEventListener('change', fetchAndRender);
document.getElementById('highlightSelect').addEventListener('change', () => {
  fetchAndRender();
  fetchTrendData();
});

// Initial load
window.onload = function () {
  const initialMeasure = document.getElementById('measureSelect').value;
  console.log('Initial measure:', initialMeasure);

  populateCostFilterOptions(); // populate LA and Region filters first
  attachCostFilterListeners(); // hook up all filter change handlers
  updateDisaggregationOptions(initialMeasure);
  fetchAndRender(); // for ASCOF tab
};

// ────────────────────────────────────────────────────────────────────────────
//  GLOBAL CHART INSTANCES
// ────────────────────────────────────────────────────────────────────────────
let costBenchmarkChart;
let costTrendChart;

// ────────────────────────────────────────────────────────────────────────────
//  MAIN FETCH + RENDER
// ────────────────────────────────────────────────────────────────────────────
function fetchAndRenderCostCharts() {
  // 1️⃣ Grab current filters --------------------------------------------------
  const laSelect = document.getElementById('costFilterLA');
  const la      = laSelect && laSelect.value ? laSelect.value.trim() : '';
  const region  = document.getElementById('costFilterRegion').value;
  const ageGroups = Array.from(document.getElementById('costFilterAge').selectedOptions).map(o => o.value);
  const setting = document.getElementById('costFilterSetting').value;
  const reason  = document.getElementById('costFilterReason').value;
  const displayMode = document.getElementById('costDisplayMode').value;


  // 2️⃣ Build querystring -----------------------------------------------------
  const params = new URLSearchParams();
  if (la)      params.append('la', la);
  if (region)  params.append('region', region);
  ageGroups.forEach(g => params.append('age_groups[]', g));
  if (setting) params.append('support_setting', setting);
  if (reason)  params.append('primary_support_reason', reason);
  params.append('display_mode', displayMode);                            

  // 3️⃣ Fetch & render --------------------------------------------------------
  fetch(`/cost-data?${params.toString()}`)
    .then(res => res.json())
    .then(data => {
      console.log('📦 cost-data response:', data);

      // ───────────────────────────────────────────────────────────
      //  COMMON FORMATTERS → £000s → £Xm
      // ───────────────────────────────────────────────────────────
      const toMillions = v => v / 1_000;                       // 1k ➜ 1m
      const tickFmt = v => `£${toMillions(v).toLocaleString()} m`;
      const tooltipFmt = raw =>
        `£${toMillions(raw).toFixed(raw >= 100_000 ? 0 : raw >= 10_000 ? 1 : 2)} m`;

      // ───────────────────────────────────────────────────────────
      //  BENCHMARK  BAR  CHART
      // ───────────────────────────────────────────────────────────
      const benchmarkCtx = document.getElementById('costBenchmarkChart').getContext('2d');
      if (costBenchmarkChart) costBenchmarkChart.destroy();

      const labels = data.benchmark.map(d => d['Geographical Description']);
      const values = data.benchmark.map(d => d['Measure_Value']);
      const selectedLA = la;

      const backgroundColors = labels.map(label =>
        label === selectedLA
          ? 'rgba(255, 99, 132, 0.8)'   // red = selected LA
          : 'rgba(54, 162, 235, 0.6)'   // blue = others
      );

      costBenchmarkChart = new Chart(benchmarkCtx, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: '£ m',               // legend label
            data: values,
            backgroundColor: backgroundColors
          }]
        },
        options: {
          responsive: true,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: ctx => tooltipFmt(ctx.parsed.y)
              }
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              title: { display: true, text: '£ millions' },
              ticks: { callback: tickFmt }
            },
            x: {
              title: { display: true, text: 'Local Authority' }
            }
          }
        }
      });

      // ───────────────────────────────────────────────────────────
      //  TREND  LINE  CHART
      // ───────────────────────────────────────────────────────────
      const trendCtx = document.getElementById('costTrendChart').getContext('2d');
      if (costTrendChart) costTrendChart.destroy();

      const buildSeries = (label, entries, color) => ({
        label,
        data: entries.map(d => ({ x: d.Year, y: d.Measure_Value })),
        borderColor: color,
        backgroundColor: color,
        tension: 0.3,
        spanGaps: true
      });

      const trendData = [];
      if (data.england?.length)
        trendData.push(buildSeries('England average', data.england, 'rgba(54, 162, 235, 0.3)'));

      if (data.region?.length) {
        const regionName = data.region[0]?.Region || 'Regional';
        trendData.push(buildSeries(`${regionName} average`, data.region, 'rgba(54, 162, 235, 0.6)'));
      }

      if (data.la?.length) {
        const selectedLAName = laSelect.options[laSelect.selectedIndex]?.text || 'Local Authority';
        trendData.push(buildSeries(selectedLAName, data.la, 'rgba(255, 99, 132, 1)'));
      }

      const allYears = new Set();
      [...(data.england || []), ...(data.region || []), ...(data.la || [])]
        .forEach(d => allYears.add(d.Year));
      const sortedYears = Array.from(allYears).sort();

      costTrendChart = new Chart(trendCtx, {
        type: 'line',
        data: { datasets: trendData },
        options: {
          responsive: true,
          interaction: { mode: 'nearest', axis: 'x', intersect: false },
          plugins: {
            legend: { display: true },
            tooltip: {
              mode: 'index',
              intersect: false,
              callbacks: {
                label: ctx => tooltipFmt(ctx.parsed.y)
              }
            }
          },
          scales: {
            x: {
              type: 'category',
              labels: sortedYears,
              offset: true,
              title: { display: true, text: 'Year' }
            },
            y: {
              beginAtZero: true,
              title: { display: true, text: '£ millions' },
              ticks: { callback: tickFmt }
            }
          }
        }
      });
    });

  // Optional: still update the subtitle (no-op if stubbed)
  updateSubtitle?.();
}

  
const fetchCostDebounced = debounce(fetchAndRenderCostCharts, 150);

function attachCostFilterListeners() {
  const selectors = [
    'costFilterLA',
    'costFilterRegion',
    'costFilterAge',
    'costFilterSetting',
    'costFilterReason',
    'costDisplayMode'
  ];

  selectors.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', () => {
      updateSubtitle();
      fetchCostDebounced();
    });
  });
}

function setActiveTab(selectedId) {
  const tabs = {
    tabAscof: {
      el: document.getElementById('tabAscof'),
      activeClasses: ['bg-blue-600', 'text-white', 'font-semibold', 'shadow-sm'],
      inactiveClasses: ['text-gray-700', 'hover:outline', 'hover:outline-2', 'hover:outline-blue-500']
    },
    tabCost: {
      el: document.getElementById('tabCost'),
      activeClasses: ['bg-blue-600', 'text-white', 'font-semibold', 'shadow-sm'],
      inactiveClasses: ['text-gray-700', 'hover:outline', 'hover:outline-2', 'hover:outline-blue-500']
    }
  };

  Object.entries(tabs).forEach(([id, { el, activeClasses, inactiveClasses }]) => {
    el.classList.remove(...activeClasses, ...inactiveClasses);
    if (id === selectedId) {
      el.classList.add(...activeClasses);
    } else {
      el.classList.add(...inactiveClasses);
    }
  });
}

document.getElementById('tabAscof').addEventListener('click', () => {
  setActiveTab('tabAscof');
  document.getElementById('ascofDashboard').classList.remove('hidden');
  document.getElementById('CostDashboard').classList.add('hidden');
});

document.getElementById('tabCost').addEventListener('click', () => {
  setActiveTab('tabCost');
  document.getElementById('ascofDashboard').classList.add('hidden');
  document.getElementById('CostDashboard').classList.remove('hidden');
  fetchCostDebounced();
});

attachCostFilterListeners();


window.addEventListener('DOMContentLoaded', () => {
  setActiveTab('tabAscof'); // preselect ASCOF
});


// 🔕 Disable the subtitle for now
function updateSubtitle() { /* no-op */ }

// Populate LA and Region filter options dynamically from existing dropdowns
function populateCostFilterOptions() {
  const laSelect     = document.getElementById('costFilterLA');
  const regionSelect = document.getElementById('costFilterRegion');

  // --- Gather every LA + its region from the hidden ASCOF dropdown ----------
  const allLAs = Array.from(document.querySelectorAll('#highlightSelect option'))
    .map(opt => ({
      name  : opt.value,
      region: opt.getAttribute('data-region')?.trim() || ''
    }))
    .filter(o => o.name);                         // skip empty option

  const allRegions = Array.from(new Set(allLAs.map(o => o.region)))
    .filter(Boolean)                              // drop blanks
    .sort();

  // --- Build Region dropdown ------------------------------------------------
  regionSelect.innerHTML = '';                    // reset
  regionSelect.appendChild(new Option('All', ''));   // default first row
  allRegions.forEach(r => regionSelect.appendChild(new Option(r, r)));

  // --- Helper to (re)populate the LA dropdown ------------------------------
  const renderLAs = (list) => {
    laSelect.innerHTML = '';
    laSelect.appendChild(new Option('None', ''));    // first row
    list
      .sort((a, b) => a.name.localeCompare(b.name))
      .forEach(({ name, region }) => {
        const opt = new Option(name, name);
        opt.setAttribute('data-region', region);
        laSelect.appendChild(opt);
      });
  };

  // Initial render: show *all* LAs
  renderLAs(allLAs);

  // --------------------------------------------------------------------------
  // REGION change logic
  //   • Filters the LA list to councils inside the chosen region.
  //   • Clears LA selection if it’s no longer valid.
  //   • Triggers chart refresh.
  // --------------------------------------------------------------------------
  regionSelect.addEventListener('change', () => {
    const region = regionSelect.value;            // '' means All
    const currentLA = laSelect.value;

    const filteredLAs = region
      ? allLAs.filter(o => o.region === region)
      : allLAs;

    renderLAs(filteredLAs);

    if (!filteredLAs.some(o => o.name === currentLA)) {
      laSelect.value = '';                        // reset LA if out of scope
    }

    // 🔄 Refresh charts with the new region filter
    fetchCostDebounced();
  });

  // --------------------------------------------------------------------------
  // LA change logic
  //   • Simply refreshes charts with the chosen LA.
  //   • Does NOT touch the Region dropdown.
  // --------------------------------------------------------------------------
  //laSelect.addEventListener('change', () => {
    // (Optional) updateSubtitle?.();
    //fetchCostDebounced();
  //});
}
