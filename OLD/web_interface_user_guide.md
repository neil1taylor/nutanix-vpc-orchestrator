# Nutanix VPC Orchestrator - Web Interface User Guide

## What is a Web Interface?

Think of a web interface like using a smartphone app instead of typing commands into a computer terminal. Instead of memorizing complex commands and typing them perfectly, you can simply click buttons, fill out forms, and see visual information on your screen.

**Before (Command Line):**
```
curl -X POST http://server:8080/api/v1/nodes -H "Content-Type: application/json" -d '{"node_config":{"node_name":"my-server"}}'
```

**After (Web Interface):**
- Open your web browser
- Click "Provision New Node" button
- Fill out a simple form
- Click "Submit"

## Getting Started

### Step 1: Opening the Web Interface

1. **Open your web browser** (Chrome, Firefox, Safari, Edge - any will work)
2. **Type in the web address** (URL) that your IT administrator provided
   - It will look something like: `http://nutanix-server.company.com:8080`
3. **Press Enter** - the Nutanix Orchestrator dashboard will load

### Step 2: Understanding What You See

When the page loads, you'll see a **dashboard** - think of it like the home screen on your phone that shows you the most important information at a glance.

## Main Areas of the Interface

### 🏠 Dashboard (Home Page)

This is your **control center** that shows:

**Statistics Cards** (the boxes at the top):
- **Active Nodes**: How many servers are currently running
- **Clusters**: How many groups of servers you have
- **Total Deployments**: How many servers you've set up total
- **Success Rate**: What percentage of setups worked correctly

**Recent Deployments Table**:
- Shows the latest servers being set up
- Each row represents one server
- **Green dots** = server is running perfectly ✅
- **Yellow dots** = server is still being set up ⏳
- **Red dots** = something went wrong ❌

### 💻 Cluster Nodes

Click "Cluster Nodes" in the top menu to see:
- **All your servers** in one list
- **Each server's details**: name, IP address, what it does, which cluster it belongs to
- **Status** of each server (healthy, setting up, etc.)
- **"Manage" buttons** to get more details about specific servers

### 🚀 Provision New Node (Adding a Server)

This is where you **add new servers**. Think of it like ordering a custom computer:

1. **Click "Provision New Node"** (the blue button)
2. **Fill out the form** with details like:
   - **Node Name**: What you want to call this server (like "Production-Server-01")
   - **Server Profile**: How powerful you want it (like choosing iPhone storage: 64GB, 128GB, 256GB)
   - **Cluster Operation**: Whether this starts a new group or joins an existing one
3. **Click "Provision Node"** to start setting it up

**Form Fields Explained:**
- **Node Name**: Just like naming a file on your computer - pick something you'll remember
- **Node Position**: Where in the rack this server sits (like apartment numbers)
- **Server Profile**: The "size" of server (more cores = faster, more RAM = can handle more at once)
- **Cluster Role**: What job this server will do (compute = processing, storage = saving files)
- **Cluster Operation**: 
  - "Create New Cluster" = Start a new group
  - "Join Existing Cluster" = Add to current group

### 📋 Deployments (Setup History)

This shows **every server setup** you've ever done:
- **When** each server was set up
- **How long** it took
- **What phase** it's currently in (like "Installing software" or "Configuring network")
- **Whether it succeeded or failed**

### 📊 Monitoring (Health Check)

This is like a **health checkup** for your whole system:
- **System Status**: Are all the background services running?
- **Performance**: How fast things are responding
- **Storage Usage**: How much disk space is being used
- **Average Setup Time**: How long new servers typically take to set up

## How to Do Common Tasks

### Adding Your First Server

1. **Go to Dashboard** (click "Dashboard" at the top)
2. **Click "Provision New Node"** (blue button in top right)
3. **Fill out the form**:
   - Node Name: `my-first-server`
   - Server Profile: Choose the middle option (good balance of power)
   - Cluster Operation: Select "Create New Cluster"
4. **Click "Provision Node"**
5. **Wait and watch**: Go to "Deployments" to see progress

### Checking on a Server Setup

1. **Click "Deployments"** in the top menu
2. **Find your server** in the list
3. **Look at the progress bar** - it shows how far along the setup is
4. **Click "View Logs"** if you want to see detailed information

### Viewing All Your Servers

1. **Click "Cluster Nodes"** in the top menu
2. **See the complete list** of all servers
3. **Click "Manage"** next to any server to see detailed information

### Adding More Servers to an Existing Group

1. **Click "Provision New Node"**
2. **Fill out the form** but this time:
   - Choose "Join Existing Cluster" for Cluster Operation
3. **Submit** - the new server will automatically join your existing group

## Understanding Status Indicators

**Color-coded dots** next to each server tell you its status:

- 🟢 **Green (Running)**: Server is working perfectly
- 🟡 **Yellow (Provisioning)**: Server is being set up right now
- 🔴 **Red (Error)**: Something went wrong during setup
- ⚪ **Gray (Stopped)**: Server is turned off or not responding

## Understanding Progress Bars

**Progress bars** show how far along a server setup is:
- **0% - Starting**: Just beginning the setup process
- **25% - Hardware Check**: Making sure the physical server is working
- **50% - Installing Foundation**: Installing the basic Nutanix software
- **75% - Network Configuration**: Setting up network connections
- **100% - Complete**: Server is ready to use!

## Troubleshooting Common Issues

### "I clicked something and nothing happened"
- **Wait a few seconds** - sometimes it takes a moment
- **Check your internet connection**
- **Refresh the page** (press F5 or click the refresh button)

### "I see a red error message"
- **Read the message** - it usually tells you what went wrong
- **Check that you filled out all required fields** (marked with *)
- **Try again** - sometimes there are temporary network issues

### "A server setup failed"
- **Click "View Logs"** to see what happened
- **Contact your IT administrator** with the server name and error message
- **The system will usually provide suggestions** on how to fix the problem

### "The page looks broken or strange"
- **Try a different web browser** (Chrome usually works best)
- **Clear your browser cache** (Google "how to clear cache" for your browser)
- **Make sure JavaScript is enabled** in your browser

## Tips for Success

### 🎯 Best Practices
- **Use descriptive names** for servers (like "Production-Web-Server-01" instead of "Server1")
- **Wait for one server to finish** before starting another (unless you need multiple)
- **Check the Monitoring page** regularly to make sure everything is healthy
- **Keep the Deployments page open** in another tab when setting up servers to watch progress

### ⚡ Keyboard Shortcuts
- **Ctrl+N**: Quick shortcut to open the "Provision New Node" form
- **Esc**: Close any popup windows
- **F5**: Refresh the page to get the latest information

### 📱 Mobile-Friendly
The interface works on tablets and phones too! The layout automatically adjusts to smaller screens.

## What Happens Behind the Scenes

When you use the web interface, here's what actually happens:

1. **You click a button** or fill out a form
2. **Your browser sends a request** to the Nutanix server
3. **The server processes your request** and starts working
4. **The server sends updates back** to your browser
5. **Your browser updates the page** to show you the current status

This all happens automatically - you don't need to understand the technical details!

## Getting Help

### Built-in Help
- **Status messages**: The interface shows helpful messages when things happen
- **Error explanations**: When something goes wrong, you'll get clear explanations
- **Progress indicators**: Always know what's happening and how long it might take

### When to Contact Support
Contact your IT administrator or system administrator if:
- **Multiple servers fail** to set up
- **The web interface won't load** at all
- **You see repeated error messages** that don't make sense
- **You need to change advanced settings** not available in the interface

### Information to Provide When Getting Help
When asking for help, provide:
- **What you were trying to do** ("I was trying to add a new server")
- **What happened instead** ("I got a red error message")
- **The exact error message** (copy and paste it)
- **The server name** you were working with
- **What web browser** you're using

## Security Notes

- **Always log out** when you're done (if there's a logout option)
- **Don't share your login credentials** with others
- **Use the interface from your company network** - don't access it from public Wi-Fi when possible
- **Close the browser tab** when finished to prevent accidental changes

## Summary

The Nutanix VPC Orchestrator web interface makes managing servers as easy as using any modern website. Instead of memorizing complex commands, you can:

- **See everything at a glance** on the dashboard
- **Click buttons** instead of typing commands
- **Fill out forms** instead of writing code
- **Watch progress in real-time** with visual indicators
- **Get helpful error messages** when something needs attention

The interface is designed to be intuitive - if you can use a smartphone or browse the internet, you can use this system to manage your Nutanix infrastructure!