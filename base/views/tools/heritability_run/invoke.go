package main

// VERSION v1

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"time"

	"cloud.google.com/go/storage"
)

const heritabilityVersion = "v1"
const datasetName = "data.tsv"
const resultName = "result.tsv"

func check(e error) {
	if e != nil {
		panic(e)
	}
}

func copyBlob(bucket string, source string, blob string) {
	ctx := context.Background()
	client, err := storage.NewClient(ctx)
	check(err)

	// source
	f, err := os.Open(source)
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()

	wc := client.Bucket(bucket).Object(blob).NewWriter(ctx)
	_, err = io.Copy(wc, f)
	check(err)
}

func fileExists(filename string) bool {
	info, err := os.Stat(filename)
	if os.IsNotExist(err) {
		return false
	}
	return !info.IsDir()
}

func runTask() {
	// Run the heritability analysis. This is used to run it in the background.
	for {
		// Execute R script
		if fileExists("hash.txt") {
			cmd := exec.CommandContext(r.Context(), "Rscript", "H2_script.R", datasetName, resultName, "hash.txt")
			cmd.Stderr = os.Stderr
			_, err := cmd.Output()
			check(err)

			// Copy results to google storage.
			datasetBlob := fmt.Sprintf("reports/heritability_%s/%s/%s", heritabilityVersion, dataHash, datasetName)
			resultBlob := fmt.Sprintf("reports/heritability_%s/%s/%s", heritabilityVersion, dataHash, resultName)
			copyBlob("elegansvariation.org", datasetName, datasetBlob)
			copyBlob("elegansvariation.org", resultName, resultBlob)
		}
		time.Sleep(1000 * time.Millisecond)
	}
}

func runH2(w http.ResponseWriter, r *http.Request) {
	/*
		Runs the herritability analysis
	*/

	// Get POST data and save as CSV
	data := r.FormValue("data")
	dataHash := r.FormValue("hash")
	f, err := os.Create(datasetName)
	check(err)
	f.WriteString(data)

	// Write the hash
	h, err := os.Create("hash.txt")
	check(err)
	h.WriteString(dataHash)

	f.Close()

	if err := json.NewEncoder(w).Encode("submitted h2"); err != nil {
		log.Printf("Error sending response: %v", err)
	}

}

func main() {

	go runTask()

	http.HandleFunc("/", runH2)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("listening on %s", port)
	log.Fatal(http.ListenAndServe(fmt.Sprintf(":%s", port), nil))
}
