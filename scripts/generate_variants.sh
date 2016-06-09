for i in `bcftools query -l $andersen_vcf`; do
    echo ${i}
    bcftools query --print-header --samples ${i} -f '%CHROM\t%POS\t%FILTER\t[%FT\t%GT\t%TGT\t%ANN]\n' ${andersen_vcf}
done;

bcftools query --exclude '%FILTER != "PASS"' --print-header -f '%CHROM\t%POS\t%REF\t%ALT[\t%TGT]\n' ${andersen_vcf} |\
awk '{ gsub("(# |\\[[0-9]+\\])","", $0); print }' |\
sed 's/:GT//g'