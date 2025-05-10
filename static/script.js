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
      const labels = data.map(d => d['Geographical Description']);
      const values = data.map(d => d['Measure_Value']);

      const ctx = document.getElementById('paretoChart').getContext('2d');
      if (chart) chart.destroy();

      chart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: 'Measure Value',
            data: values,
            backgroundColor: 'rgba(54, 162, 235, 0.6)'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            tooltip: { enabled: true },
            legend: { display: false }
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
    });
}

function updateDisaggregationOptions(measure) {
    fetch(`/disaggregation-options?measure=${encodeURIComponent(measure)}`)
      .then(res => res.json())
      .then(options => {
        const disaggSelect = document.getElementById('disaggSelect');
        disaggSelect.innerHTML = '';
  
        options.forEach(opt => {
          const option = document.createElement('option');
          option.value = opt;
          option.textContent = opt;
          disaggSelect.appendChild(option);
        });
  
        // Default to 'Total' if present, else first option
        if (options.includes('Total')) {
          disaggSelect.value = 'Total';
        } else if (options.length > 0) {
          disaggSelect.value = options[0];
        }
  
        fetchAndRender(); // Refresh chart with new disagg
      });
  }

function generateSummary() {
    const council = document.getElementById('councilSelect').value;

    fetch(`/mistral-summary?council=${encodeURIComponent(council)}`)
      .then(res => res.json())
      .then(data => {
        const output = document.getElementById('mistralSummary');
        if (data.summary) {
          output.innerText = data.summary;
        } else {
          output.innerText = 'No summary generated.';
        }
      })
      .catch(err => {
        console.error(err);
        document.getElementById('mistralSummary').innerText = 'An error occurred while generating the summary.';
      });
  }
    

// Event listeners
document.getElementById('measureSelect').addEventListener('change', function () {
    updateDisaggregationOptions(this.value);
  });
document.getElementById('regionSelect').addEventListener('change', fetchAndRender);
document.getElementById('disaggSelect').addEventListener('change', fetchAndRender);

// Initial render
window.onload = function () {
    const initialMeasure = document.getElementById('measureSelect').value;
    updateDisaggregationOptions(initialMeasure);
  };
