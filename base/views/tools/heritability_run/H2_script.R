#!/usr/bin/env Rscript H2_script.R
library(boot)
library(lme4)
library(dplyr)
library(futile.logger)

########################
### define functions ###
########################
# Heritability
# data is data frame that contains strain and Value column
# indicies are used by the boot function to sample from the 'data' data.frame
H2.test.boot <- function(data, indicies){
  
  d <- data[indicies,]
  
  pheno <- as.data.frame(dplyr::select(d, Value))[,1]
  
  Strain <- as.factor(d$Strain)
  
  reffMod <- lme4::lmer(pheno ~ 1 + (1|Strain))
  
  Variances <- as.data.frame(lme4::VarCorr(reffMod, comp = "Variance"))
  
  Vg <- Variances$vcov[1]
  Ve <- Variances$vcov[2]
  H2 <- Vg/(Vg+Ve)
  
  # errors <- sqrt(diag(lme4::VarCorr(reffMod, comp = "Variance")$strain))
  
  return(H2)
}

# data is data frame that contains strain and Value column
H2.test <- function(data){
  
  pheno <- as.data.frame(dplyr::select(data, Value))[,1]
  Strain <- as.factor(data$Strain)
  
  reffMod <- lme4::lmer(pheno ~ 1 + (1|Strain))
  
  Variances <- as.data.frame(lme4::VarCorr(reffMod, comp = "Variance"))
  
  Vg <- Variances$vcov[1]
  Ve <- Variances$vcov[2]
  H2 <- Vg/(Vg+Ve)
  
  # errors <- sqrt(diag(lme4::VarCorr(reffMod, comp = "Variance")$strain))
  
  return(H2)
}

# df is data frame that contains strain and Value column
H2.calc <- function(data, boot = TRUE){
  df <- dplyr::select(data, Strain, Value)
  
  flog.info("Running bootstrapping")
  if(boot == TRUE){
    # bootstrapping with 10000 replications
    # can reduce value to save time (500 is reasonable most of the time).
    # if you Error in bca.ci(boot.out, conf, index[1L], L = L, t = t.o, t0 = t0.o,  : estimated adjustment 'a' is NA, then you need to increase R value.
    results <- boot(data=df, statistic=H2.test.boot, R=10000) 
    
    # get 95% confidence interval
    ci <- boot.ci(results, type="bca")
    
    H2_errors <- data.frame(H2 = ci$t0,
                            ci_l = ci$bca[4],
                            ci_r = ci$bca[5])
    
    return(H2_errors)
    
  } else {
    H2 <- data.frame(H2 = H2.test(data = df), ci_l = NA, ci_r = NA)
    return(H2)
  }
  
}

# RUN
args = commandArgs(trailingOnly=TRUE)
usage_cmd = "USAGE: Rscprit H2_script.R input_file output_file"
if (length(args) < 2){
  print(usage_cmd)
}

# Read in data
input_data = args[1]
output_fname = args[2]
hash = args[3]
heritability_version = args[4]
data <- data.table::fread(input_data)
hash <- readLines(hash)

# Run H2 calculation
result <- H2.calc(data, boot = T)

result$hash <- hash
result$trait_name <- data$traitName[[0]]
result$date <- Sys.time()
result$heritability_version <- Sys.time()

# Write the result
data.table::fwrite(result, output_fname, sep = '\t')
