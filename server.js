const express = require("express");
const { spawn } = require("child_process");
const chokidar = require("chokidar");
const path = require("path");
const { Pool } = require("pg");
const { console } = require("inspector");
const app = express();
const PORT = 3000;

// PostgreSQL Database Connection
const pool = new Pool({
  user: "postgres",
  host: "localhost",
  database: "hackhub",
  password: "sandeep@12345",
  port: 5432,
});

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));
app.use(express.static(path.join(__dirname, "public")));

app.get('/form', (req, res) => {
  res.render('form');
});

app.get('/about', (req, res) => {
  res.render('about');
});

app.get('/service', (req, res) => {
  res.render('service');
});

app.get('/team', (req, res) => {
  res.render('team');
});
app.get('/tickket', (req, res) => {
  res.render('tickket');
});

app.get('/why', (req, res) => {
  res.render('why');
});

// Folder to watch for MKV files
const WATCH_FOLDER = "C:/Users/saisa/OneDrive/Documents/linphone/captures";

// Function to process MKV file with Python script
const processMKVFile = (filePath, callback) => {
  console.log(`Processing file: ${filePath}`);

  const pythonProcess = spawn("python", ["sample.py", filePath]);

  let outputData = "";

  pythonProcess.stdout.on("data", (data) => {
    outputData += data.toString();
  });

  pythonProcess.stderr.on("data", (data) => {
    console.error(`Python Error: ${data}`);
  });

  pythonProcess.on("close", (code) => {
    if (code === 0) {
      try {
        const resultDict = JSON.parse(outputData);
        console.log("Processing complete:", resultDict);
        callback(null, resultDict);  // Success callback with result
      } catch (error) {
        callback(new Error("Error parsing Python script output"));  // Callback with error
      }
    } else {
      callback(new Error("Python script failed"));  // Callback with failure
    }
  });
};

// Function to insert processed data into the database
const insertIntoDatabase = (data, callback) => {
  const query = `
    INSERT INTO complaints (issue, urgency, location, issuetype, status, sentiment, suggestions, pnr_number)
    VALUES ($1, $2, $3, $4, 'Pending', $5, $6, $7)
    RETURNING *;
  `;
  const values = [data.issue, data.urgency, data.location, data.issueType, data.sentiment, data.suggestion, data.PNR];

  pool.query(query, values, (err, result) => {
    if (err) {
      console.error("Database insertion error:", err.message);
      callback(err);  // Error callback
    } else {
      console.log("Data inserted into database:", result.rows[0]);
      callback(null, result.rows[0]);  // Success callback
    }
  });
};

// Watch for new MKV files and process them
chokidar.watch(WATCH_FOLDER, { persistent: true, ignoreInitial: true })
  .on("add", (filePath) => {
    if (filePath.endsWith(".mkv")) {
      console.log(`New file detected: ${filePath}`);
      processMKVFile(filePath, (error, processedData) => {
        if (error) {
          console.error("Error processing file:", error.message);
        } else {
          insertIntoDatabase(processedData, (dbError, dbResult) => {
            if (dbError) {
              console.error("Error inserting data into database:", dbError.message);
            } else {
              console.log("Inserted data:", dbResult);
            }
          });
        }
      });
    }
  });

// Routes

app.get('/', (req, res) => {
  res.render('index');
});

app.get("/dashboard", async (req, res) => {
  try {
    const result = await pool.query("SELECT * FROM complaints");
    res.render("dashboard", { complaints: result.rows });
  } catch (err) {
    console.error("Error fetching complaints:", err.message);
    res.status(500).send("Internal Server Error");
  }
});

// Check database connection
pool.query("SELECT NOW()", (err, result) => {
  if (err) {
    console.error("Database connection error:", err.message);
  } else {
    console.log("Database connected:", result.rows[0]);
  }
});


app.get("/complaints", (req, res) => {
  db.query("SELECT * FROM complaints WHERE status != 'completed'", (err, results) => {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.json(results);
  });
});



app.post('/markCompleted/:id', async (req, res) => {
  const complaintId = req.params.id; // Extracting the complaint ID from the URL
  
  try {
    // Database query to update the complaint's status
    const result = await pool.query('UPDATE complaints SET status = $1 WHERE i_id = $2', ['Completed', complaintId]);
    
    // Check if any rows were affected (i.e., the complaint exists and was updated)
    if (result.rowCount > 0) {
      res.status(200).json({ message: 'Complaint marked as completed' });
    } else {
      res.status(404).json({ message: 'Complaint not found' });
    }
  } catch (err) {
    console.error('Error updating status:', err);
    res.status(500).json({ message: 'Error marking complaint as completed' });
  }
});



app.get('/filterComplaints', async (req, res) => {
  const { urgency, location, issuetype, sentiment } = req.query;

  // Build the query dynamically based on the filters
  let query = 'SELECT * FROM complaints WHERE 1=1';
  const params = [];

  if (urgency) {
    query += ' AND urgency = $' + (params.length + 1);
    params.push(urgency);
  }
  if (location) {
    query += ' AND location = $' + (params.length + 1);
    params.push(location);
  }
  if (issuetype) {
    query += ' AND issuetype = $' + (params.length + 1);
    params.push(issuetype);
  }
  if (sentiment) {
    query += ' AND sentiment = $' + (params.length + 1);
    params.push(sentiment);
  }

  try {
    // Execute the query with the dynamic parameters
    const result = await pool.query(query, params);
    res.json({ complaints: result.rows });
  } catch (err) {
    console.error('Error filtering complaints:', err);
    res.status(500).send('Internal Server Error');
  }
});

app.get('/getTicketData/:pnr', async (req, res) => {
  const pnr = req.params.pnr;
  try {
    const result = await pool.query('SELECT * FROM tickets WHERE pnr_number = $1', [pnr]);
    if (result.rows.length > 0) {
      res.json({ success: true, ticket: result.rows[0] });
    } else {
      res.json({ success: false });
    }
  } catch (err) {
    console.error('Error fetching ticket data:', err);
    res.status(500).send('Server Error');
  }
});



// Start server
app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});
