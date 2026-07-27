	if mod.stopped {
		fmt.Println()
		color.New(color.BgBlack, color.Bold, color.FgHiRed).Println(" 🛑 Stopped early ")
		fmt.Println()
		term.PrintCmds("", "log", "rewind", "tell")
		os.Exit(0)
	} else if mod.background {
		fmt.Println()
		color.New(color.BgBlack, color.Bold, color.FgHiGreen).Println(" ✅ Plan is active in the background ")
		fmt.Println()
		term.PrintCmds("", "ps", "connect", "stop")
		os.Exit(0)
	}

	if os.Getenv("PLANDEX_REPL") != "" && os.Getenv("PLANDEX_REPL_OUTPUT_FILE") != "" {
		// write output to file
		err := os.WriteFile(os.Getenv("PLANDEX_REPL_OUTPUT_FILE"), []byte(mod.reply), 0644)
		if err != nil {
			log.Println("stream UI - error writing output to repl temp file: ", err)
		}
	}
