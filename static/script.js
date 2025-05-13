let chart;
let trendChart;

function fetchAndRender() {
  const measure = document.getElementById('measureSelect').value;
  const regionOptions = document.getElementById('regionSelect').selectedOptions;
  const regions = Array.from(regionOptions).map(opt => opt.value);
  const disagg = document.getElementById('disaggSelect').value;
  

  const params = new URLSearchParams();
  params.append('measure', measure);
  if (disagg && disagg !== '') {
    params.append('disagg', disagg);
  }
  regions.forEach(r => params.append('regions[]', r));

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

      names.forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
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
              display: true,
              text: measure,
              font: { size: 16, weight: 'bold' },
              padding: { bottom: 16 }
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

      updateLATable(selectedHighlight || '');
      fetchTrendData();  // also update trend graph
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
              display: true,
              text: `${measure} trend over time`,
              font: { size: 16, weight: 'bold' },
              padding: { bottom: 16 }
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

  loading.classList.remove('hidden');
  container.classList.add('hidden');

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
  fetchTrendData();
});
document.getElementById('regionSelect').addEventListener('change', fetchAndRender);
document.getElementById('disaggSelect').addEventListener('change', fetchAndRender);
document.getElementById('highlightSelect').addEventListener('change', () => {
  fetchAndRender();
  fetchTrendData();
});

// Initial load
window.onload = function () {
  const initialMeasure = document.getElementById('measureSelect').value;
  updateDisaggregationOptions(initialMeasure);
  fetchTrendData();
};
