// script.js
let chart;

function fetchAndRender() {
  const measure = document.getElementById('measureSelect').value;
  const regionOptions = document.getElementById('regionSelect').selectedOptions;
  const regions = Array.from(regionOptions).map(opt => opt.value);
  const disagg = document.getElementById('disaggSelect').value;

  const params = new URLSearchParams();
  params.append('measure', measure);
  params.append('disagg', disagg);
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
        sortField: {
          field: 'text',
          direction: 'asc'
        },
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
              font: {
                size: 16,
                weight: 'bold'
              },
              padding: {
                bottom: 16
              }
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              title: {
                display: true,
                text: 'Value'
              }
            },
            x: {
              title: {
                display: true,
                text: 'Council'
              }
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

      const hasOptions = options.length > 0;

      if (hasOptions) {
        options.forEach(opt => {
          const option = document.createElement('option');
          option.value = opt;
          option.textContent = opt;
          disaggSelect.appendChild(option);
        });

        disaggSelect.disabled = false;
        disaggSelect.classList.remove('bg-gray-100', 'text-gray-400');
        disaggSelect.classList.add('bg-white');

        if (options.includes('Total')) {
          disaggSelect.value = 'Total';
        } else {
          disaggSelect.value = options[0];
        }
      } else {
        disaggSelect.disabled = true;
        disaggSelect.classList.remove('bg-white');
        disaggSelect.classList.add('bg-gray-100', 'text-gray-400');

        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No data available';
        disaggSelect.appendChild(option);
        disaggSelect.value = '';
      }

      fetchAndRender();
    });
}

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

function updateLATable(selectedLA) {
  const params = new URLSearchParams();
  if (selectedLA) params.append('la', selectedLA);

  fetch(`/la-outcomes?${params.toString()}`)
    .then(res => res.json())
    .then(data => {
      const container = document.getElementById('laMeasuresTable');
      if (!data.length) {
        container.innerHTML = '<p class="text-gray-600 text-sm">No data available.</p>';
        return;
      }

      const rows = data.map(row => `
        <tr class="border-b">
          <td class="px-4 py-2 text-sm">${row['Measure Group Description']}</td>
          <td class="px-4 py-2 text-sm">${parseFloat(row['Measure_Value']).toFixed(2)}</td>
          <td class="px-4 py-2 text-sm">${Math.round(row['Percentile'])}th</td>
          <td class="px-4 py-2 text-sm">${row['Direction']}</td>
        </tr>
      `).join('');

      container.innerHTML = `
        <table class="min-w-full text-left border rounded mt-6">
          <thead class="bg-gray-100">
            <tr>
              <th class="px-4 py-2 text-sm font-medium">Measure</th>
              <th class="px-4 py-2 text-sm font-medium">Value</th>
              <th class="px-4 py-2 text-sm font-medium">Percentile</th>
              <th class="px-4 py-2 text-sm font-medium">Better Direction</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    });
}
