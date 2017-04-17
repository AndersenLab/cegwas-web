# NEW API

from cendr import api, cache, app, autoconvert
from cyvcf2 import VCF
from flask import jsonify, request
import re
import sys
from cendr.models import wb_gene
from cendr.views.api.gene import get_gene_region
from tempfile import NamedTemporaryFile
from subprocess import Popen, PIPE

ANN_header = ["allele",
              "effect",
              "impact",
              "gene_name",
              "gene_id",
              "feature_type",
              "feature_id",
              "transcript_biotype",
              "exon_intron_rank",
              "nt_change",
              "aa_change",
              "cDNA_position/cDNA_len",
              "protein_position",
              "distance_to_feature",
              "error"]

GT_zip = ['SAMPLE', 'TGT', 'GT', 'FT']

def get_region(region):
    region = region.replace(",", "")
    m = re.match("^([0-9A-Za-z]+):([0-9]+)-([0-9]+)$", region)
    if m:
        chrom = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3))
        gene = None
    else:
        # Resolve gene/location
        gene = get_gene_region(region)
        if not gene:
            return "Invalid region", 400
        chrom = gene["CHROM"]
        start = gene["start"]
        end = gene["end"]
    region = "{chrom}:{start}-{end}".format(**locals())
    return region, chrom, start, end, gene


@app.route('/api/variant/<region>')
@app.route('/api/variant/<region>')
def variant_api(region, tracks = "mh"):
    version = request.args.get('version') or 20170312
    samples = request.args.get('samples')
    vcf = "http://storage.googleapis.com/elegansvariation.org/releases/{version}/WI.{version}.vcf.gz".format(
        version=version)
    region, chrom, start, end, gene = get_region(region)

    if start >= end:
        return "Invalid start and end region values", 400
    if end - start > 1e5:
        return "You can only query a maximum of 100 kb", 400

    comm = ["bcftools", "view", vcf, region]

    # Query samples
    if samples:
        comm = comm[0:2] + ['--force-samples', '--samples', samples] + comm[2:]
        print(comm)

    out, err = Popen(comm, stdout=PIPE, stderr=PIPE).communicate()
    print(out)
    tfile = NamedTemporaryFile()
    json_out = []
    with tfile as f:
        f.write(out)
        v = VCF(tfile.name)

        if samples:
            samples = samples.split(",")
            incorrect_samples = [x for x in samples if x not in v.samples]
            if incorrect_samples:
                return "Incorrectly specified sample(s): " + ','.join(incorrect_samples), 400

        for record in v:
            INFO = dict(record.INFO)
            if "ANN" in INFO.keys():
                ANN_set = INFO['ANN'].split(",")
                del INFO['ANN']
                for ANN_rec in ANN_set:
                    ANN = dict(zip(ANN_header, ANN_rec.split("|")))
                    gt_set = zip(v.samples, record.gt_bases.tolist(), record.gt_types.tolist(), record.format("FT").tolist())
                    gt_set = [dict(zip(GT_zip, x)) for x in gt_set]
                    json_out.append({
                        "CHROM": record.CHROM,
                        "POS": record.POS,
                        "REF": record.REF,
                        "ALT": record.ALT,
                        "GT": gt_set,
                        "INFO": INFO,
                        "ANN": ANN
                    })
    return jsonify(json_out)
