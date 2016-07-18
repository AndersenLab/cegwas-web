from flask import Flask, Response, request
from flask_restful import Resource, Api, reqparse
from cendr import api
from cendr.models import *
from collections import OrderedDict, Counter
from gcloud import storage
import decimal
import json
import datetime
# import urllib2
import os
import sys
from peewee import JOIN
from dateutil.parser import parse
import zlib, cPickle, base64

FIELDS = [x.name for x in strain._meta.sorted_fields if x.name != "id"]
PEEWEE_FIELDS_LIST = [getattr(strain, x.name)
                      for x in strain._meta.sorted_fields if x.name != "id"]



class CustomEncoder(json.JSONEncoder):

    def default(self, o):
        if type(o) == decimal.Decimal:
            return float(o)
        if isinstance(o, datetime.date):
            return str(o)
        return super(CustomEncoder, self).default(o)

parser = reqparse.RequestParser()

def wb_gene_getter(chrom = None, name = None , start = None, end = None, sequence_name = None,locus = None):
    if sequence_name:
        filtrate = (wb_gene.sequence_name == sequence_name)

    elif locus:
        filtrate = (wb_gene.locus == locus)

    elif name:
        filtrate = (wb_gene.Name == name)

    else:
        if start > end:
            return "Error :( Reason: start point is greater than end point in your query."
        filtrate = ( (wb_gene.CHROM == chrom) 
                    and (wb_gene.start >= start) 
                    and (wb_gene.end <= end) )

    result = list(wb_gene.select(wb_gene.CHROM ,wb_gene.Name, wb_gene.start,
                                 wb_gene.end,wb_gene.sequence_name,wb_gene.locus)
                                .filter(filtrate) 
                                .dicts()
                                .execute())
    return result

class individual_wb_gene_get(Resource):
    def get(self, chrom = None, name = None , start = None, end = None, sequence_name = None, locus = None):
        wb_genes = wb_gene_getter(chrom,name,start,end,sequence_name, locus)
        if type(wb_genes)  == list:
            fields = ["CHROM","Name", "start", "end", "sequence_name", "locus"]
            dat = json.dumps(wb_genes, cls=CustomEncoder, indent=4)
            return Response(response=dat,status=200, mimetype="application/json")
        else:
            return Response(response=wb_genes, status=404)

api.add_resource(individual_wb_gene_get, '/api/individual_wb_gene/interval/<string:chrom>/<int:start>/<int:end>'
                ,'/api/individual_wb_gene/sequence_name/<string:sequence_name>'
                ,'/api/individual_wb_gene/name/<string:name>'
                ,'/api/individual_wb_gene/locus/<string:locus>')


#=========#
# MAPPING #
#=========#


class mapping_api(Resource):

    def get(self):
        reports = list(mapping.select(mapping.chrom,
                                      mapping.pos,
                                      mapping.interval_start,
                                      mapping.interval_end,
                                      mapping.log10p,
                                      mapping.variance_explained,
                                      mapping.BF,
                                      mapping.reference,
                                      mapping.version).join(report).filter(report.release == 0).tuples().execute())

        fields = ["chrom", "pos", "interval_start", "interval_end",
                  "log10p", "variance_explained", "BF", "reference", "version"]
        reports = [OrderedDict(zip(fields, x)) for x in reports]
        dat = json.dumps(reports, cls=CustomEncoder, indent=4)
        return Response(response=dat, status=200, mimetype="application/json")

api.add_resource(mapping_api, '/api/mapping')


#========#
# Strain #
#========#

class strain_api(Resource):

    def get(self):
        strain_data = list(strain.select(
            *PEEWEE_FIELDS_LIST).tuples().execute())
        strain_data = [OrderedDict(zip(FIELDS, x)) for x in strain_data]
        dat = json.dumps(strain_data, cls=CustomEncoder, indent=4)
        return Response(response=dat, status=200, mimetype="application/json")


api.add_resource(strain_api, '/api/strain')


class strain_ind_api(Resource):

    def get(self, strain_name):
        strain_data = list(strain.select(
            *PEEWEE_FIELDS_LIST).filter(strain.strain == strain_name).tuples().execute())
        strain_data = OrderedDict(zip(FIELDS, strain_data[0]))
        dat = json.dumps(strain_data, cls=CustomEncoder, indent=4)
        return Response(response=dat, status=200, mimetype="application/json")


api.add_resource(strain_ind_api, '/api/strain/<string:strain_name>')


class isotype_ind_api(Resource):

    def get(self, isotype_name):
        strain_data = list(strain.select(
            strain.strain).filter(strain.isotype == isotype_name).execute())
        strain_data = [x.strain for x in strain_data]
        dat = json.dumps(strain_data, cls=CustomEncoder, indent=4)
        return Response(response=dat, status=200, mimetype="application/json")


api.add_resource(isotype_ind_api, '/api/strain/isotype/<string:isotype_name>')


class report_by_date(Resource):

    def get(self, date):
        data = list(trait.select(report.report_slug, report.report_name, trait.trait_name, trait.trait_slug, report.release, trait.submission_complete).join(
            report).filter((db.truncate_date("day", trait.submission_complete) == parse(date).date()), (report.release == 0), trait.status == "complete").dicts().execute())
        dat = json.dumps(data, cls=CustomEncoder, indent=4)
        return Response(response=dat, status=200, mimetype="application/json")

api.add_resource(report_by_date, '/api/report/date/<string:date>')

class report_progress(Resource):

    def post(self, trait_slug, report_slug=None, report_hash=None):
        queue = get_queue()
        current_status = list(trait.select(trait.status)
                              .join(report)
                              .filter(trait.trait_slug == trait_slug, ((report.report_slug == report_slug) and (report.release == 0)) | (report.report_hash == report_hash))
                              .dicts()
                              .execute())[0]["status"]
        if trait_slug:
            try:
                trait_data = [x for x in report_data if x[
                    'trait_slug'] == trait_slug[0]]
            except:
                return Response(response="", status=404, catch_all_404s=True)
            title = trait_data["report_name"]
            subtitle = trait_data["trait_name"]

            if trait_data["release"] == 0:
                report_url_slug = trait_data["report_slug"]
            else:
                report_url_slug = trait_data["report_hash"]
        else:

            try:
                first_trait = list(report_data)[0]
            except:
                return Response(response="", status=404, catch_all_404s=True)

        report_slug = trait_data["report_slug"]
        base_url = "https://storage.googleapis.com/cendr/" + report_slug + "/" + trait_slug

        report_files = list(storage.Client().get_bucket("cendr").list_blobs(
            prefix=report_slug + "/" + trait_slug + "/tables"))
        report_files = [os.path.split(x.name)[1] for x in report_files]

        report_url = base_url + "/report.html"
        report_html = requests.get(report_url).text.replace(
            'src="', 'src="' + base_url + "/")

        if not report_html.startswith("<?xml"):
            report_html = report_html[report_html.find("<body>"):report_html.find("</body")].replace(
                "</body", " ").replace("<body>", "").replace('<h1 class="title">cegwas results</h1>', "")
        else:
            report_html = ""
        return Response(response=report_html, status=200, mimetype="application/json")

reports_urls = ['/api/<string:report_slug>/<string:trait_slug>',
                '/api/<string:report_slug>/<string:trait_slug>']


#==========#
# Variants #
#==========#


#
# GT
#

class get_gt(Resource):
    def get(self, chrom, pos):
        gt = cPickle.loads(zlib.decompress(base64.b64decode(WI.get(WI.CHROM == chrom, WI.POS == pos).GT)))
        result = json.dumps(gt, indent = 4)
        return Response(response=result, status=201, mimetype="application/json")

api.add_resource(get_gt, '/api/variant/gt/<string:chrom>/<int:pos>')


def decode_gt(gt):
    return cPickle.loads(zlib.decompress(base64.b64decode(gt)))

#
# GT By Location
#

def fetch_geo_gt(chrom, pos):
    gt = decode_gt(WI.get(WI.CHROM == chrom, WI.POS == pos).GT)
    strain_locations = list(strain.select(strain.isotype, strain.latitude, strain.longitude)
        .filter(strain.latitude != None)
        .distinct().dicts().execute())
    strain_locations = {x["isotype"]:x for x in strain_locations}
    for i in gt:
        if i["SAMPLE"] in strain_locations and i["GT"] in ["0/0", "1/1"]:
            strain_locations[i["SAMPLE"]].update({"TGT": i["TGT"], "GT": i["GT"]})
        else:
            if i["SAMPLE"] in strain_locations:
                del strain_locations[i["SAMPLE"]]
    return strain_locations.values()

class strain_gt_locations(Resource):
    def get(self, chrom, pos):
        result = fetch_geo_gt(chrom, pos)
        result = json.dumps(result, indent = 4)
        return Response(response=result, status = 200, mimetype="application/json")

api.add_resource(strain_gt_locations, '/api/variant/gtloc/<string:chrom>/<int:pos>')


#
# Get Genotypes from Interval
#

def gt_from_interval(chrom, start, end, var_eff):
    print var_eff
    result = list(WI.select(WI.CHROM, 
                            WI.POS,
                            WI.FILTER, 
                            WI.putative_impact, 
                            WI.gene_id, 
                            WI.hgvs_p,
                            WI.protein_position,
                            WI.GT,
                            WI.feature_id,
                            WI.annotation,
                            wb_gene).filter(WI.CHROM == chrom,
                                          WI.POS >= start,
                                          WI.POS <= end,
                                          WI.putative_impact << var_eff).join(wb_gene, on = (WI.gene_name == wb_gene.Name)).limit(1000).dicts().execute())
    for i in result:
        i["GT"] = decode_gt(i["GT"])
    return result

class fetch_gt_from_interval(Resource):
    def get(self, chrom, start, end, tracks=""):
        if tracks:
            putative_impact = {'l': 'LOW', 'm':'MODERATE', 'h': 'HIGH'}
            var_eff = [putative_impact[x] if x else '' for x in tracks]
            result = gt_from_interval(chrom, start, end, var_eff)
            result = json.dumps(result)
        else:
            result = ""
        return Response(response=result, status = 200, mimetype="application/json")

urls = ['/api/variant/gt/<string:chrom>/<int:start>/<int:end>/<string:tracks>','/api/variant/gt/<string:chrom>/<int:start>/<int:end>/']

api.add_resource(fetch_gt_from_interval,*urls)

#
# Tajima's D
#

class tajima_d(Resource):
  def get(self, chrom, start, end):
    data = list(tajimaD.select(tajimaD.BIN_START, tajimaD.TajimaD).filter((tajimaD.CHROM == chrom) &
                                                         (tajimaD.BIN_START >= start - 50000) &
                                                         (tajimaD.BIN_END <= end + 50000),
                                                         ).tuples().execute())
    data = [(int(x[0]) + 50000, float(x[1])) for x in data]
    data = {"x": [x[0] for x in data], "y": [x[1] for x in data]}
    dat = json.dumps(data, cls=CustomEncoder, indent = 4)
    return Response(response=dat, status=200, mimetype="application/json")

api.add_resource(tajima_d, '/api/variant/tajima/<string:chrom>/<int:start>/<int:end>')

#
# wb_gene info
#

class get_gene(Resource):
    def get(self, gene):
        result = list(wb_gene.filter((wb_gene.Name == gene) |
                                (wb_gene.sequence_name == gene) |
                                (wb_gene.locus == gene))
                        .dicts()
                        .execute())
        ordered = OrderedDict()
        if len(result) == 1:
            order = [x.name for x in wb_gene._meta.sorted_fields if x.name != "id"]
            for k in order:
                ordered[k] = result[0][k]
            result = json.dumps(ordered, cls=CustomEncoder, indent=4)
            return Response(response=result, status=200, mimetype="application/json")

api.add_resource(get_gene, '/api/gene/<string:gene>')

class get_gene_count(Resource):
    def get(self, chrom, start, end):
        count_by_type = list(wb_gene.select(wb_gene.biotype,
                                            fn.Count(wb_gene.id).alias('count'))
                            .filter((wb_gene.CHROM == chrom),
                                      (wb_gene.start > start),
                                      (wb_gene.end < end)).group_by(wb_gene.biotype).tuples().execute())
        count = sum([x[1] for x in count_by_type])
        result = OrderedDict((("chrom", chrom),
                    ("start", start),
                    ("end", end),
                    ("total", count)))
        result.update(dict(count_by_type))
        result = json.dumps(result, cls=CustomEncoder, indent=4)
        return Response(response=result, status=200, mimetype="application/json")

api.add_resource(get_gene_count, '/api/gene/count/<string:chrom>/<int:start>/<int:end>')

class fetch_gene_list(Resource):
    def get(self, chrom, start, end):
        gene_list = list(wb_gene.select(wb_gene.CHROM,
                                        wb_gene.start,
                                        wb_gene.end,
                                        wb_gene.Name,
                                        wb_gene.sequence_name,
                                        wb_gene.biotype,
                                        wb_gene.locus)
                                        .filter((wb_gene.CHROM == chrom),
                                      (wb_gene.start > start),
                                      (wb_gene.end < end)).tuples().execute())
        wb_gene_fields = [x.name for x in wb_gene._meta.sorted_fields if x.name != "id"]
        gene_list = [OrderedDict(zip(wb_gene_fields, x)) for x in gene_list]
        gene_count = len(gene_list)
        result = OrderedDict((("chrom", chrom),
                    ("start", start),
                    ("end", end),
                    ("count", gene_count),
                    ("gene_list", gene_list)))
        result = json.dumps(result, cls=CustomEncoder, indent=4)
        return Response(response=result, status=200, mimetype="application/json")

api.add_resource(fetch_gene_list, '/api/genelist/<string:chrom>/<int:start>/<int:end>')

#
# Variants
#

def get_gene_list(chrom, start, end):
    """
        Return genes from a given interval
    """
    return list(wb_gene.select().where(
                                ((wb_gene.CHROM == chrom) & (wb_gene.start >= start) & (wb_gene.end <= end)) |
                                ((wb_gene.CHROM == chrom) & (wb_gene.start <= start) & (wb_gene.end >= start)) |
                                ((wb_gene.CHROM == chrom) & (wb_gene.end >= end) & (wb_gene.end <= start))
                            ).dicts().distinct().execute())


def get_gene_w_variants(chrom, start, end, impact):
    """
        Return Genes with variants of given impact for a given interval
    """
    return {x["gene_name"]:x for x in list(WI.select(WI.gene_name, WI.putative_impact).where(
                   WI.putative_impact == impact, 
                   WI.CHROM == chrom,
                   WI.POS >= start,
                   WI.POS <= end
                   )
                  .distinct()
                  .dicts().execute())}


def get_variant_count(chrom, start, end):
    """
        Return the number of variants within an interval
    """
    return WI.select(WI.id).filter(WI.CHROM == chrom, WI.POS >= start, WI.POS <= end).count()


def interval_summary(chrom, start, end):
    try:
        g_interval = intervals.get(intervals.CHROM == chrom, intervals.BIN_START == start, intervals.BIN_END == end)
    except:
        gene_list = get_gene_list(chrom, start, end)
        moderate_variants = get_gene_w_variants(chrom, start, end, "MODERATE")
        high_gene_variants = get_gene_w_variants(chrom, start, end, "HIGH")
        r = {}
        for i in gene_list:
            if i["Name"] in moderate_variants:
                i.update({"moderate_effect": True})
            if i["Name"] in high_gene_variants:
                i.update({"high_effect": True})
        r["ALL"] = dict(Counter([x["biotype"] for x in gene_list]))
        r["MODERATE"] = dict(Counter([x["biotype"] for x in gene_list if "moderate_effect" in x]))
        r["HIGH"] = dict(Counter([x["biotype"] for x in gene_list if "high_effect" in x]))
        g_interval = intervals()
        for k,v in r["ALL"].items():
            setattr(g_interval, "ALL_" + k, v)
        for k,v in r["MODERATE"].items():
            setattr(g_interval, "MODERATE_" + k, v)
        for k,v in r["HIGH"].items():
            setattr(g_interval, "HIGH_" + k, v)
        setattr(g_interval, "ALL_Total", sum(r["ALL"].values()))
        setattr(g_interval, "MODERATE_Total", sum(r["MODERATE"].values()))
        setattr(g_interval, "HIGH_Total", sum(r["HIGH"].values()))
        g_interval.CHROM = chrom
        g_interval.BIN_START = start
        g_interval.BIN_END = end
        g_interval.N_VARIANTS = get_variant_count(chrom, start, end)
        try:
            g_interval.save()
        except:
            # Retrieve interval; failures likely due to duplicates.
            g_interval = intervals.get(intervals.CHROM == chrom, intervals.BIN_START == start, intervals.BIN_END == end)
    return g_interval

class get_interval_summary(Resource):
    def get(self, chrom, start, end):
        g_interval = interval_summary(chrom, start, end)
        result = OrderedDict()
        for x in intervals._meta.sorted_field_names:
            if x != "id":
                result[x] = getattr(g_interval, x)
        result = json.dumps(result, indent = 4)
        return Response(response=result, status=200, mimetype="application/json")


api.add_resource(get_interval_summary, '/api/interval/<string:chrom>/<int:start>/<int:end>')


class search_homologs(Resource):
    def get(self, term):
        hgene_results = list(homologene.filter(
                          (homologene.gene_symbol == term) or
                          (homologene.protein_gi == term) or
                          (homologene.protein_accession == term))
                          .select(homologene.gene_symbol,
                                  homologene.ce_ortholog,
                                  homologene.species)
                          .distinct()
                          .dicts().execute())

        #wbgene_results = list(wb_gene.filter(
        #                      (wb_gene.gene == term) or
        #                      (wb_gene.ortholog == term))
        #                      .select(wb_gene.gene,
        #                              wb_gene.ce_ortholog,
        #                              wb_gene.species)


        #result = json.dumps(hgene_results, indent = 4, cls=CustomEncoder)



        return Response(response = result, status = 200, mimetype="application/json")

api.add_resource(search_homologs, '/api/homolog/<string:term>')

