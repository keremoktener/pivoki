using ImageMagick;
using Pivoki.Core;

internal static class PackageBridgeChecks
{
    internal static async Task Run(string root,Action<bool,string> check)
    {
        var prior=Environment.GetEnvironmentVariable("PIVOKI_DATA_DIR");
        Environment.SetEnvironmentVariable("PIVOKI_DATA_DIR",Path.Combine(root,"package-profile"));
        try
        {
            var list=await PackageEngine.RequestAsync(new{action="packages"});
            check(list.Packages.Length>0,"Package list did not round trip");
            var outputs=new[]{new PackageOutput("webp",1600,"web"),new PackageOutput("jpg",400,"küçük")};
            var pkg=(await PackageEngine.RequestAsync(new{action="savePackage",package=new{name="Çekim",outputs}})).Package!;
            check(pkg.Name=="Çekim"&&pkg.Outputs.SequenceEqual(outputs),"Unicode package rows did not round trip");
            var source=Path.Combine(root,"A & B ürün.png");
            using(var image=new MagickImage(MagickColors.ForestGreen,640,240))image.Write(source);
            var outRoot=Path.Combine(root,"teslim");
            var plan=await PackageEngine.RequestAsync(new{action="plan",inputs=new[]{source},outputRoot=outRoot,
                packageId=pkg.PackageId,revision=pkg.Revision,conflictPolicy="keep-both",recursive=false});
            check(plan.Rows.Length==2&&plan.InputCount==1&&!Directory.Exists(outRoot),"Planning must keep output paths reserved only in the plan");
            var completed=await PackageEngine.RequestAsync(new{action="run",planId=plan.PlanId});
            check(completed.Status=="success" && completed.Paths.SequenceEqual(plan.Rows.Select(row=>row.Target)),"Published files diverged from the approved plan");
            using(var small=new MagickImage(completed.Paths[1]))check(small.Width==400&&small.Height==150,"The independent verification reader found the wrong dimensions");
            var jobs=(await PackageEngine.RequestAsync(new{action="history"})).Jobs;
            check(jobs.Length==1 && jobs[0].Paths.SequenceEqual(completed.Paths),"Expected one complete package result");
            await PackageEngine.RequestAsync(new{action="removeHistory",jobId=jobs[0].JobId});
            check(completed.Paths.All(File.Exists)&&(await PackageEngine.RequestAsync(new{action="history"})).Jobs.Length==0,"Deleting history affected files");
            var cancelPlan=await PackageEngine.RequestAsync(new{action="plan",inputs=new[]{source},outputRoot=outRoot,packageId=pkg.PackageId,revision=pkg.Revision});
            var marker=Path.Combine(root,"cancel-request");File.WriteAllText(marker,"cancel");
            var cancelled=await PackageEngine.RequestAsync(new{action="run",planId=cancelPlan.PlanId,cancelFile=marker});
            check(cancelled.Status=="cancelled"&&completed.Paths.All(File.Exists),"Cancelled run touched an earlier job");
        }
        finally{Environment.SetEnvironmentVariable("PIVOKI_DATA_DIR",prior);}
    }
}
