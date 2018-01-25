#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Author: Daniel E. Cook



"""
import glob
import os
import arrow
from utils.gcloud import report_m
from subprocess import Popen, STDOUT, PIPE

# Create a data directory
if not os.path.exists('data'):
    os.makedirs('data')

def run_comm(comm):
    print("Running comm")
    process = Popen(comm, stdout=PIPE, stderr=STDOUT)
    with process.stdout as proc:
        for line in proc:
            print(str(line, 'utf-8').strip())
    return process

# Define variables
report_name = os.environ['REPORT_NAME']
trait_name = os.environ['TRAIT_NAME']
print(f"Fetching Task: {report_name} - {trait_name}")
report = report_m(os.environ['REPORT_NAME'])
trait = report.fetch_traits(trait_name=trait_name, latest=True)


try:
    report._trait_df[['STRAIN', trait_name]].to_csv('df.tsv', sep='\t', index=False)
    # Update report start time
    trait.started_on = arrow.utcnow().datetime
    trait.run_status = "Running"
    trait.save()

    comm = ['Rscript', 'pipeline.R']
    process = run_comm(comm)
    exitcode = process.wait()

    print(f"R exited with code {exitcode}")

    # Mark trait significant/insignificant
    trait.is_significant = True

    # Upload datasets
    trait.upload_files(glob.glob("data/*"))


except Exception as e:
    trait.error_message = e
    trait.run_status = "Error"
else:
    trait.run_status = "Complete"
finally:
    trait.completed_on = arrow.utcnow().datetime
    trait.save()