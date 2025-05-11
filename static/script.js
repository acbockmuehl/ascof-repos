let chart;

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

        if (options.includes('Total')) {
          disaggSelect.value = 'Total';
        } else {
          disaggSelect.value = '';
        }
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

// Ordinal suffix helper
function formatOrdinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

// Colour scale from red → amber → green
function getPercentileColor(percentile, direction) {
  const scale = direction === "Higher is better"
    ? percentile / 100
    : 1 - percentile / 100;

  const interpolateHex = (start, mid, end, t) => {
    const [r1, g1, b1] = start;
    const [r2, g2, b2] = mid;
    const [r3, g3, b3] = end;

    if (t < 0.5) {
      t *= 2;
      return `rgb(${Math.round(r1 + (r2 - r1) * t)}, ${Math.round(g1 + (g2 - g1) * t)}, ${Math.round(b1 + (b2 - b1) * t)})`;
    } else {
      t = (t - 0.5) * 2;
      return `rgb(${Math.round(r2 + (r3 - r2) * t)}, ${Math.round(g2 + (g3 - g2) * t)}, ${Math.round(b2 + (b3 - b2) * t)})`;
    }
  };

  return interpolateHex([237, 121, 121], [255, 202, 110], [120, 196, 116], scale);
}

function updateLATable(selectedLA) {
  const params = new URLSearchParams();
  if (selectedLA) params.append('la', selectedLA);

  fetch(`/la-outcomes?${params.toString()}`)
    .then(res => res.json())
    .then(data => {
      const container = document.getElementById('laMeasuresTable');

      // 🆕 Only keep rows where Disaggregation Level is "Total" or blank/null
      const totalOnly = data.filter(row => {
        const level = row['Disaggregation Level'];
        return !level || level.trim().toLowerCase() === 'total';
      });

      if (!totalOnly.length) {
        container.innerHTML = '<p class="text-gray-600 text-sm">No total-level benchmarking data available for this council.</p>';
        return;
      }

      // 🟢 Colour interpolation helpers
      function interpolateColor(color1, color2, factor) {
        const c1 = color1.match(/\w\w/g).map(hex => parseInt(hex, 16));
        const c2 = color2.match(/\w\w/g).map(hex => parseInt(hex, 16));
        const result = c1.map((v, i) => Math.round(v + factor * (c2[i] - v)));
        return `rgb(${result[0]}, ${result[1]}, ${result[2]})`;
      }

      const RED = '#ed7979';
      const AMBER = '#ffca6e';
      const GREEN = '#78c474';

      const rows = totalOnly.map(row => {
        const isProportion = row['Measure Group Description']?.toLowerCase().startsWith('proportion');
        const value = parseFloat(row['Measure_Value']);
        const formattedValue = isProportion
          ? `${Math.round(value)}%`
          : value.toFixed(2);

        const percentile = Math.round(row['Percentile_National']) || 0;
        const direction = row['Direction']?.toLowerCase();
        const normalised = direction === 'lower is better' ? 100 - percentile : percentile;

        // Interpolate colour: 0–50 = red → amber, 50–100 = amber → green
        let percentileColor = AMBER;
        if (normalised < 50) {
          const factor = normalised / 50;
          percentileColor = interpolateColor(RED, AMBER, factor);
        } else {
          const factor = (normalised - 50) / 50;
          percentileColor = interpolateColor(AMBER, GREEN, factor);
        }

        const ordinal = (() => {
          const s = ["th", "st", "nd", "rd"];
          const v = percentile % 100;
          return percentile + (s[(v - 20) % 10] || s[v] || s[0]);
        })();

        return `
          <tr class="border-b">
            <td class="px-4 py-2 text-sm">${row['Measure Group']}</td>
            <td class="px-4 py-2 text-sm">${row['Measure Group Description']}</td>
            <td class="px-4 py-2 text-sm">${formattedValue}</td>
            <td class="px-4 py-2 text-sm" style="background-color: ${percentileColor};">${ordinal}</td>
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
    });
}


// Event listeners
document.getElementById('measureSelect').addEventListener('change', function () {
  updateDisaggregationOptions(this.value);
});
document.getElementById('regionSelect').addEventListener('change', fetchAndRender);
document.getElementById('disaggSelect').addEventListener('change', fetchAndRender);
document.getElementById('highlightSelect').addEventListener('change', fetchAndRender);

window.onload = function () {
  const initialMeasure = document.getElementById('measureSelect').value;
  updateDisaggregationOptions(initialMeasure);
};
